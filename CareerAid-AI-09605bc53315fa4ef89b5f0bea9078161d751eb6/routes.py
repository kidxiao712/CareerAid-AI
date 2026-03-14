from __future__ import annotations

import io
import json
import os
import secrets
from datetime import datetime
from typing import Any, Optional

import pdfplumber
from docx import Document
from flask import Blueprint, jsonify, request, send_file
from docx import Document as DocxDocument

from ai_client import AIClient
from ai_helper import AIHelper, _safe_json_dumps
from career_graph import build_echarts_data, list_all_families
from database import db
from models import Student, Job, MatchResult, Report, ChatMessage


api = Blueprint("api", __name__)

TOKENS: dict[str, int] = {}


def _get_bearer_token() -> str:
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        return auth.split(" ", 1)[1].strip()
    return ""


def _require_student() -> Student:
    token = _get_bearer_token()
    student_id = TOKENS.get(token)
    if not student_id:
        raise PermissionError("未登录或登录已过期")
    student = db.session.get(Student, student_id)
    if not student:
        raise PermissionError("用户不存在")
    return student


def _json_error(message: str, status: int = 400):
    return jsonify({"ok": False, "error": message}), status


def _read_docx_bytes(data: bytes) -> str:
    f = io.BytesIO(data)
    doc = Document(f)
    parts = []
    for p in doc.paragraphs:
        t = (p.text or "").strip()
        if t:
            parts.append(t)
    return "\n".join(parts)


def _read_pdf_bytes(data: bytes) -> str:
    f = io.BytesIO(data)
    parts = []
    with pdfplumber.open(f) as pdf:
        for page in pdf.pages[:10]:
            txt = page.extract_text() or ""
            if txt.strip():
                parts.append(txt)
    return "\n".join(parts)


def _seed_jobs_if_empty(ai: AIHelper) -> None:
    if db.session.query(Job).count() > 0:
        return

    samples = [
        {
            "title": "数据分析实习生",
            "industry": "互联网/数据",
            "salary": "150-200/天",
            "requirements_text": "熟悉Excel/SQL，了解Python数据分析，良好沟通，能做可视化报表。",
        },
        {
            "title": "后端开发工程师（校招）",
            "industry": "互联网/软件",
            "salary": "12-20K",
            "requirements_text": "掌握Python/Java至少一种，熟悉Flask/Django或Spring，理解数据库与缓存，了解Linux与Git。",
        },
        {
            "title": "前端开发工程师（校招）",
            "industry": "互联网/软件",
            "salary": "12-20K",
            "requirements_text": "熟悉JavaScript/TypeScript，掌握React或Vue，了解工程化与性能优化，有作品集优先。",
        },
        {
            "title": "产品助理",
            "industry": "互联网/产品",
            "salary": "10-16K",
            "requirements_text": "具备用户调研与需求分析能力，良好沟通与推动，能写PRD，会用原型工具。",
        },
        {
            "title": "算法工程师（NLP方向）",
            "industry": "AI/算法",
            "salary": "18-35K",
            "requirements_text": "熟悉机器学习/深度学习，掌握PyTorch，了解NLP/LLM，具备论文复现与工程落地能力。",
        },
    ]

    for s in samples:
        job = Job(
            title=s["title"],
            industry=s.get("industry"),
            salary=s.get("salary"),
            requirements_text=s.get("requirements_text"),
            job_profile_json=_safe_json_dumps(ai.generate_job_profile(s)),
        )
        db.session.add(job)

    db.session.commit()


def _get_ai() -> AIHelper:
    return AIHelper(client=AIClient())


@api.errorhandler(PermissionError)
def _handle_perm(e):
    return _json_error(str(e), status=401)


@api.route("/login", methods=["POST"])
def login():
    payload = request.get_json(silent=True) or {}
    username = (payload.get("username") or "").strip()
    password = (payload.get("password") or "").strip()

    if username != "admin" or password != "123456":
        return _json_error("用户名或密码错误（测试账号：admin / 123456）", status=401)

    student = db.session.query(Student).filter_by(username=username).one_or_none()
    if not student:
        student = Student(username=username, name="测试用户", major="计算机相关")
        db.session.add(student)
        db.session.commit()

    token = secrets.token_urlsafe(24)
    TOKENS[token] = student.id

    return jsonify({"ok": True, "token": token, "student_id": student.id, "student": student.to_dict()})


@api.route("/upload_resume", methods=["POST"])
def upload_resume():
    student = _require_student()
    ai = _get_ai()
    _seed_jobs_if_empty(ai)

    manual = {
        "major": (request.form.get("major") or "").strip(),
        "skills": (request.form.get("skills") or "").strip(),
        "certs": (request.form.get("certs") or "").strip(),
        "internships": (request.form.get("internships") or "").strip(),
    }
    resume_text = (request.form.get("resume_text") or "").strip()

    file = request.files.get("resume_file")
    if file and file.filename:
        filename = file.filename.lower()
        data = file.read()
        if filename.endswith(".docx"):
            resume_text = (resume_text + "\n" + _read_docx_bytes(data)).strip()
        elif filename.endswith(".pdf"):
            resume_text = (resume_text + "\n" + _read_pdf_bytes(data)).strip()
        elif filename.endswith(".jpg") or filename.endswith(".jpeg") or filename.endswith(".png"):
            # OCR 依赖较重，这里先存档提示；企业需要 OCR 时可接入 PaddleOCR/Tesseract
            resume_text = (resume_text + "\n" + "（已上传图片简历：当前版本未启用OCR解析，请在手动录入区补充关键信息。）").strip()
        else:
            return _json_error("仅支持 docx/pdf/jpg/png 文件")

    if not resume_text:
        return _json_error("请上传简历文件或手动录入简历信息")

    parsed = ai.parse_resume(resume_text, manual=manual)

    if manual.get("major"):
        student.major = manual["major"]
    student.resume_raw_text = resume_text
    student.resume_parsed_json = _safe_json_dumps(parsed)
    db.session.commit()

    # 写入一条 AI 引导消息（回到 chat.html 不丢失）
    db.session.add(
        ChatMessage(
            student_id=student.id,
            role="ai",
            content="简历解析完成！你的个人能力画像已生成，点击【性格测评】完善你的职业偏好吧～",
        )
    )
    db.session.commit()

    return jsonify({"ok": True, "student_id": student.id, "resume_parsed": parsed})


@api.route("/submit_test", methods=["POST"])
def submit_test():
    student = _require_student()
    payload = request.get_json(silent=True) or {}
    student.personality_test_json = _safe_json_dumps(payload)
    db.session.commit()

    db.session.add(
        ChatMessage(
            student_id=student.id,
            role="ai",
            content="职业偏好已完善，我会结合你的简历和测评做精准人岗匹配，结果会在【岗位列表】中标注匹配度哦～",
        )
    )
    db.session.commit()
    return jsonify({"ok": True, "student_id": student.id})


@api.route("/jobs", methods=["GET"])
def get_jobs():
    student: Optional[Student] = None
    try:
        student = _require_student()
    except Exception:
        student = None

    ai = _get_ai()
    _seed_jobs_if_empty(ai)

    q = (request.args.get("q") or "").strip().lower()
    include_match = (request.args.get("include_match") or "").strip() in {"1", "true", "yes"}

    query = db.session.query(Job)
    if q:
        like = f"%{q}%"
        query = query.filter((Job.title.like(like)) | (Job.industry.like(like)) | (Job.requirements_text.like(like)))

    jobs = query.order_by(Job.id.asc()).limit(200).all()
    out = []

    student_profile = None
    if include_match and student and student.resume_parsed_json:
        try:
            student_profile = json.loads(student.resume_parsed_json)
        except Exception:
            student_profile = None

    for j in jobs:
        item = j.to_dict()
        if include_match and student_profile:
            try:
                job_profile = json.loads(j.job_profile_json or "{}")
            except Exception:
                job_profile = ai.generate_job_profile(item)
            m = ai.match(student_profile, job_profile)
            item["match_preview"] = {"score": m.get("score", 0), "reasoning": m.get("reasoning", "")}
        out.append(item)

    return jsonify({"ok": True, "jobs": out})


@api.route("/jobs/<int:job_id>", methods=["GET"])
def job_detail(job_id: int):
    job = db.session.get(Job, job_id)
    if not job:
        return _json_error("岗位不存在", status=404)
    return jsonify({"ok": True, "job": job.to_dict()})


@api.route("/me", methods=["GET"])
def me():
    student = _require_student()
    data = student.to_dict()
    try:
        data["resume_parsed"] = json.loads(student.resume_parsed_json or "{}")
    except Exception:
        data["resume_parsed"] = {}
    try:
        data["personality_test"] = json.loads(student.personality_test_json or "{}")
    except Exception:
        data["personality_test"] = {}
    return jsonify({"ok": True, "student": data})


@api.route("/match_jobs", methods=["POST"])
def match_jobs():
    student = _require_student()
    ai = _get_ai()
    _seed_jobs_if_empty(ai)

    payload = request.get_json(silent=True) or {}
    goal = (payload.get("goal") or "").strip()

    if not student.resume_parsed_json:
        return _json_error("请先上传/录入简历并解析")

    try:
        student_profile = json.loads(student.resume_parsed_json)
    except Exception:
        return _json_error("简历解析数据损坏，请重新上传解析")

    jobs = db.session.query(Job).order_by(Job.id.asc()).all()
    results = []

    # 清理旧匹配（演示版：每次重算覆盖）
    db.session.query(MatchResult).filter(MatchResult.student_id == student.id).delete()
    db.session.commit()

    for j in jobs:
        job_dict = j.to_dict()
        try:
            job_profile = json.loads(j.job_profile_json or "{}")
        except Exception:
            job_profile = ai.generate_job_profile(job_dict)
            j.job_profile_json = _safe_json_dumps(job_profile)
            db.session.add(j)

        matched = ai.match(student_profile, job_profile)
        dim_full = matched.get("dimension_scores") or {}
        dim_4 = matched.get("dimension_scores_4") or {}
        mr = MatchResult(
            student_id=student.id,
            job_id=j.id,
            score=float(matched.get("score") or 0),
            dimension_scores_json=_safe_json_dumps({"dimension_scores": dim_full, "dimension_scores_4": dim_4}),
            gap_analysis_json=_safe_json_dumps(matched.get("gap_analysis") or {}),
            reasoning=matched.get("reasoning") or "",
        )
        db.session.add(mr)
        results.append(
            {
                "job_id": j.id,
                "job_title": j.title,
                "industry": j.industry,
                "salary": j.salary,
                "score": mr.score,
                "dimension_scores": dim_full,
                "dimension_scores_4": dim_4,
                "gap_analysis": matched.get("gap_analysis") or {},
                "reasoning": mr.reasoning,
            }
        )

    db.session.commit()

    results.sort(key=lambda x: x["score"], reverse=True)
    return jsonify({"ok": True, "student_id": student.id, "goal": goal, "matches": results})


@api.route("/generate_report", methods=["POST"])
def generate_report():
    student = _require_student()
    ai = _get_ai()
    _seed_jobs_if_empty(ai)

    payload = request.get_json(silent=True) or {}
    goal = (payload.get("goal") or "").strip()

    if not student.resume_parsed_json:
        return _json_error("请先上传/录入简历并解析")

    # 取已有匹配或先计算
    match_rows = (
        db.session.query(MatchResult)
        .filter(MatchResult.student_id == student.id)
        .order_by(MatchResult.score.desc())
        .limit(5)
        .all()
    )
    if not match_rows:
        # 自动计算一次
        _ = match_jobs()
        match_rows = (
            db.session.query(MatchResult)
            .filter(MatchResult.student_id == student.id)
            .order_by(MatchResult.score.desc())
            .limit(5)
            .all()
        )

    top_matches = []
    for mr in match_rows:
        job = db.session.get(Job, mr.job_id)
        try:
            dims = json.loads(mr.dimension_scores_json or "{}")
            dim_scores = dims.get("dimension_scores") or dims
            dim_scores_4 = dims.get("dimension_scores_4") or {}
        except Exception:
            dim_scores = {}
            dim_scores_4 = {}
        top_matches.append(
            {
                "job_id": mr.job_id,
                "job_title": job.title if job else f"job#{mr.job_id}",
                "score": mr.score,
                "gap_analysis": json.loads(mr.gap_analysis_json or "{}"),
                "dimension_scores": dim_scores,
                "dimension_scores_4": dim_scores_4,
                "reasoning": mr.reasoning,
            }
        )

    student_dict = student.to_dict()
    content = ai.generate_report(student_dict, top_matches, goal=goal)

    from ai_helper import report_completeness_check
    check = report_completeness_check(content)

    report = Report(student_id=student.id, content=content)
    db.session.add(report)
    db.session.commit()

    return jsonify(
        {
            "ok": True,
            "report_id": report.id,
            "content": content,
            "download_url": f"/download_report/{report.id}",
            "download_docx_url": f"/download_report_docx/{report.id}",
            "completeness_check": check,
            "created_at": datetime.utcnow().isoformat(),
        }
    )


@api.route("/career_graph", methods=["GET"])
def career_graph():
    """岗位关联图谱：垂直晋升 + 换岗路径。至少 5 个岗位族，每族不少于 2 条换岗路径。"""
    title = (request.args.get("title") or "").strip()
    if title:
        data = build_echarts_data(title)
        return jsonify({"ok": True, "graph": data, "families": list_all_families()})
    return jsonify({"ok": True, "families": list_all_families(), "graph": build_echarts_data(None)})


@api.route("/chat/history", methods=["GET"])
def chat_history():
    student = _require_student()
    limit = int(request.args.get("limit") or 50)
    rows = (
        db.session.query(ChatMessage)
        .filter(ChatMessage.student_id == student.id)
        .order_by(ChatMessage.id.asc())
        .limit(max(1, min(limit, 300)))
        .all()
    )
    return jsonify({"ok": True, "messages": [r.to_dict() for r in rows]})


def _offline_agent_reply(student: Student, user_text: str) -> str:
    # 离线兜底：给出引导+可执行建议（不联网）
    if not student.resume_parsed_json:
        return "我可以先帮你解析简历生成能力画像。请点击顶部【简历上传】上传/录入简历信息。"
    if not student.personality_test_json:
        return "我已拿到你的简历画像。建议再做一次【性格测评】补充职业偏好，我会基于两者做更精准的人岗匹配。"
    t = (user_text or "").strip()
    if "报告" in t:
        return "你可以点击顶部【报告生成】一键生成职业生涯发展报告（含目标与行动计划），并支持下载。"
    if "岗位" in t or "匹配" in t:
        return "我建议你先在【岗位列表】查看匹配度较高的岗位，并进入【匹配结果】页查看 TOP5、雷达图与差距清单。"
    return "你可以问我：市场岗位能力要求、我的优势与短板、推荐岗位与差距、以及分阶段行动计划。"


@api.route("/chat/send", methods=["POST"])
def chat_send():
    student = _require_student()
    payload = request.get_json(silent=True) or {}
    user_text = (payload.get("text") or "").strip()
    if not user_text:
        return _json_error("消息不能为空")

    # 存用户消息
    db.session.add(ChatMessage(student_id=student.id, role="user", content=user_text))
    db.session.commit()

    ai = _get_ai()
    client = ai.client

    # 拼接上下文：学生画像 + 最近对话
    history_rows = (
        db.session.query(ChatMessage)
        .filter(ChatMessage.student_id == student.id)
        .order_by(ChatMessage.id.desc())
        .limit(20)
        .all()
    )
    history = list(reversed(history_rows))

    # 简易联网搜索：当用户询问“市场要求/竞赛/趋势/怎么学”等，补充检索摘要
    search_block = ""
    keywords = ["市场", "趋势", "要求", "竞赛", "证书", "学习路线", "怎么学", "什么是", "是什么"]
    if any(k in user_text for k in keywords):
        results = client.web_search(user_text, limit=5) if hasattr(client, "web_search") else []
        if results:
            lines = [f"- {r.get('title','')}（{r.get('url','')}）" for r in results]
            search_block = "【联网检索参考】\n" + "\n".join(lines) + "\n"

    system_prompt = (
        "你是大学生 AI 职业规划助手。你的目标：\n"
        "1) 帮学生快速了解就业市场/岗位能力要求并可拆解；\n"
        "2) 准确分析学生就业能力与意愿；\n"
        "3) 给出明确可操作的建议（行动计划、补齐差距、作品集/投递/面试策略）。\n\n"
        "要求：输出中文；回答要具体、可执行、可解释；尽量引用“数据/事实/来源链接”（若提供了联网检索参考）。\n"
    )

    context = {
        "student": student.to_dict(),
        "resume_parsed_json": student.resume_parsed_json,
        "personality_test_json": student.personality_test_json,
        "search": search_block,
        "recent_messages": [{"role": m.role, "content": m.content} for m in history],
    }
    user_prompt = (
        f"{search_block}"
        f"【学生信息与画像】\n{_safe_json_dumps(context)}\n\n"
        f"【本轮用户问题】\n{user_text}\n\n"
        "请结合学生画像与对话历史回答，并给出下一步操作引导（例如：去简历上传/性格测评/岗位列表/报告生成）。"
    )

    reply = ""
    try:
        reply = client.chat_text(system_prompt, user_prompt)
    except Exception:
        reply = _offline_agent_reply(student, user_text)

    db.session.add(ChatMessage(student_id=student.id, role="ai", content=reply))
    db.session.commit()

    return jsonify({"ok": True, "reply": reply})


@api.route("/download_report/<int:report_id>", methods=["GET"])
def download_report(report_id: int):
    student = _require_student()
    report = db.session.get(Report, report_id)
    if not report or report.student_id != student.id:
        return _json_error("报告不存在", status=404)

    data = report.content.encode("utf-8")
    return send_file(
        io.BytesIO(data),
        as_attachment=True,
        download_name=f"career_report_{report_id}.txt",
        mimetype="text/plain; charset=utf-8",
    )


@api.route("/download_report_docx/<int:report_id>", methods=["GET"])
def download_report_docx(report_id: int):
    student = _require_student()
    report = db.session.get(Report, report_id)
    if not report or report.student_id != student.id:
        return _json_error("报告不存在", status=404)

    doc = DocxDocument()
    for line in (report.content or "").splitlines():
        doc.add_paragraph(line)

    bio = io.BytesIO()
    doc.save(bio)
    bio.seek(0)
    return send_file(
        bio,
        as_attachment=True,
        download_name=f"career_report_{report_id}.docx",
        mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )

