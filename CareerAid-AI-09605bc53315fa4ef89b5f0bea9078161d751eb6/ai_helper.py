from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from typing import Any, Optional

from ai_client import AIClient


def _safe_json_dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


# 不少于 10 个就业岗位/学生能力画像维度（与任务要求一致）
PROFILE_DIMENSIONS = [
    "专业技能",
    "证书要求",
    "创新能力",
    "学习能力",
    "抗压能力",
    "沟通能力",
    "实习能力",
    "团队协作",
    "问题解决",
    "职业稳定性",
]

# 人岗匹配四维度及权重：基础要求、职业技能、职业素养、发展潜力
MATCH_DIMENSIONS_4 = ["基础要求", "职业技能", "职业素养", "发展潜力"]
# 按你给的比赛要求：基础要求（40%）+ 职业技能（30%）+ 职业素养（20%）+ 发展潜力（10%）
MATCH_WEIGHTS_4 = {"基础要求": 0.4, "职业技能": 0.3, "职业素养": 0.2, "发展潜力": 0.1}
# 10 维到 4 维的映射（用于加权汇总）
DIM10_TO_DIM4 = {
    "专业技能": "职业技能",
    "证书要求": "基础要求",
    "创新能力": "发展潜力",
    "学习能力": "发展潜力",
    "抗压能力": "职业素养",
    "沟通能力": "职业素养",
    "实习能力": "职业技能",
    "团队协作": "职业素养",
    "问题解决": "职业素养",
    "职业稳定性": "发展潜力",
}


def _tokenize(text: str) -> list[str]:
    if not text:
        return []
    t = re.sub(r"[\r\n\t]+", " ", text)
    t = re.sub(r"[，。；;、/|()（）【】\\[\\]{}<>“”\"'`~!@#$%^&*+=?：:.-]+", " ", t)
    parts = [p.strip().lower() for p in t.split(" ") if p.strip()]
    return parts


def _extract_skills(text: str) -> list[str]:
    if not text:
        return []
    skills = set()
    candidates = re.findall(r"(python|java|c\\+\\+|c#|javascript|typescript|sql|mysql|postgres|mongodb|redis|flask|django|fastapi|spring|react|vue|node|docker|kubernetes|linux|git|excel|powerbi|tableau|pytorch|tensorflow|nlp|llm|prompt|数据分析|机器学习|深度学习|自然语言处理|产品|运营|市场|测试|前端|后端|算法|数据)", text, flags=re.I)
    for c in candidates:
        skills.add(c.lower())
    # 兼容“技能：xxx, yyy”写法
    m = re.search(r"(技能|skill|skills)[:：]\\s*(.+)", text, flags=re.I)
    if m:
        tail = m.group(2)[:200]
        for p in re.split(r"[，,、;；/\\s]+", tail):
            p = p.strip()
            if 1 <= len(p) <= 24:
                skills.add(p.lower())
    return sorted(skills)


def _extract_certs(text: str) -> list[str]:
    if not text:
        return []
    certs = set()
    for pat in [r"CET-?4", r"CET-?6", r"计算机二级", r"PMP", r"软考", r"教师资格证", r"ACCA", r"CPA"]:
        if re.search(pat, text, flags=re.I):
            certs.add(pat.upper().replace("\\", ""))
    m = re.search(r"(证书|cert|certs)[:：]\\s*(.+)", text, flags=re.I)
    if m:
        tail = m.group(2)[:200]
        for p in re.split(r"[，,、;；/\\s]+", tail):
            p = p.strip()
            if 1 <= len(p) <= 30:
                certs.add(p)
    return sorted(certs)


def offline_parse_resume(text: str, manual: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    manual = manual or {}
    skills = _extract_skills(text + " " + (manual.get("skills") or ""))
    certs = _extract_certs(text + " " + (manual.get("certs") or ""))
    internships = manual.get("internships") or ""

    major = manual.get("major") or ""
    if not major:
        m = re.search(r"(专业|major)[:：]\s*([\u4e00-\u9fa5A-Za-z0-9\-\s]{2,40})", text)
        if m:
            major = m.group(2).strip()

    # 10 维能力画像 + 完整度与竞争力评分
    dims = {}
    dims["专业技能"] = min(100, 25 + 7 * len(skills))
    dims["证书要求"] = min(100, 30 + 15 * len(certs))
    dims["创新能力"] = 50
    dims["学习能力"] = 58
    dims["抗压能力"] = 52
    dims["沟通能力"] = 55
    dims["实习能力"] = 65 if internships else 40
    dims["团队协作"] = 54
    dims["问题解决"] = 52
    dims["职业稳定性"] = 50

    filled = sum(1 for v in [major, skills, certs, internships] if v) if isinstance(skills, list) else 0
    completeness = min(100, 20 + 25 * filled + (15 if skills else 0) + (10 if certs else 0))
    competitiveness = min(100, sum(dims.values()) // 10)

    profile = {
        "major": major or None,
        "skills": skills,
        "certs": certs,
        "internships": internships,
        "highlights": [s for s in (skills[:8] if isinstance(skills, list) else [])],
        "dimensions": dims,
        "completeness_score": round(completeness, 1),
        "competitiveness_score": round(competitiveness, 1),
    }
    return profile


def offline_generate_job_profile(job: dict[str, Any]) -> dict[str, Any]:
    req = (job.get("requirements_text") or "") + " " + (job.get("title") or "") + " " + (job.get("job_desc") or "")
    skills = _extract_skills(req)
    certs = _extract_certs(req)
    # 不少于 10 维岗位画像
    dims = {}
    dims["专业技能"] = min(100, 60 + 4 * len(skills))
    dims["证书要求"] = min(100, 30 + 12 * len(certs))
    dims["创新能力"] = 55
    dims["学习能力"] = 62
    dims["抗压能力"] = 58
    dims["沟通能力"] = 60
    dims["实习能力"] = 55
    dims["团队协作"] = 58
    dims["问题解决"] = 58
    dims["职业稳定性"] = 52
    profile = {
        "title": job.get("title"),
        "industry": job.get("industry"),
        "key_skills": skills[:12],
        "cert_requirements": certs[:6] if certs else [],
        "dimensions": dims,
        "summary": f"该岗位关注：{', '.join(skills[:8])}" if skills else "该岗位关注通用能力与业务理解。",
    }
    return profile


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 0.0
    return len(a & b) / max(1, len(a | b))


def offline_match(student_profile: dict[str, Any], job_profile: dict[str, Any]) -> dict[str, Any]:
    s_skills = set((student_profile.get("skills") or []))
    j_skills = set((job_profile.get("key_skills") or []))
    skill_overlap = _jaccard(s_skills, j_skills)

    s_dim = student_profile.get("dimensions") or {}
    j_dim = job_profile.get("dimensions") or {}
    dim_scores = {}
    for k in PROFILE_DIMENSIONS:
        sv = float(s_dim.get(k, 50))
        jv = float(j_dim.get(k, 50))
        diff = abs(sv - jv)
        dim_scores[k] = round(max(0.0, 100.0 - diff * 1.2), 1)

    # 四维度能力分析并加权综合：基础要求、职业技能、职业素养、发展潜力
    dim4_scores = {}
    for d4 in MATCH_DIMENSIONS_4:
        vals = [dim_scores.get(d10, 50) for d10, parent in DIM10_TO_DIM4.items() if parent == d4]
        dim4_scores[d4] = round(sum(vals) / max(1, len(vals)), 1)
    weighted = sum(MATCH_WEIGHTS_4.get(d, 0) * (dim4_scores.get(d, 0) / 100.0) for d in MATCH_DIMENSIONS_4)
    raw = 0.6 * weighted + 0.4 * skill_overlap
    score = round(100.0 * min(1.0, (1.0 / (1.0 + math.exp(-6 * (raw - 0.35))))), 1)

    missing = sorted(list(j_skills - s_skills))[:10]
    gap = {
        "missing_skills": missing,
        "suggestions": [
            f"优先补齐：{', '.join(missing[:5])}" if missing else "继续巩固核心技能，准备项目/面试材料。",
            "用 1-2 个作品集项目证明能力（含 README、截图、部署链接）。",
            "针对目标岗位 JD 做简历关键词优化与 STAR 案例准备。",
        ],
    }
    reasoning = "；".join([f"{d}={dim4_scores.get(d, 0)}%" for d in MATCH_DIMENSIONS_4]) + f"；技能重叠{round(skill_overlap*100,1)}%。"

    return {
        "score": score,
        "dimension_scores": dim_scores,
        "dimension_scores_4": dim4_scores,
        "gap_analysis": gap,
        "reasoning": reasoning,
    }


def offline_generate_report(
    student: dict[str, Any], top_matches: list[dict[str, Any]], goal: str = ""
) -> str:
    name = student.get("name") or student.get("username") or "同学"
    major = student.get("major") or ""
    goal = goal or "找到与自身优势匹配的高成长岗位"

    lines = []
    lines.append("职业生涯发展报告（AI 生成）")
    lines.append("")
    lines.append("一、基本信息")
    lines.append(f"- 姓名/账号：{name}")
    if major:
        lines.append(f"- 专业：{major}")
    lines.append(f"- 职业目标：{goal}")
    lines.append("")

    lines.append("二、学生就业能力画像")
    try:
        resume_profile = json.loads(student.get("resume_parsed_json") or "{}")
    except Exception:
        resume_profile = {}
    dims = resume_profile.get("dimensions") or {}
    if dims:
        lines.append("- 能力维度得分（0-100）：")
        for k in PROFILE_DIMENSIONS:
            if k in dims:
                lines.append(f"  - {k}：{dims[k]}")
    comp = resume_profile.get("completeness_score") or resume_profile.get("competitiveness_score")
    if comp is not None:
        lines.append(f"- 画像完整度/竞争力评分：{comp}")
    skills = resume_profile.get("skills") or []
    if skills:
        lines.append(f"- 关键技能：{', '.join(skills[:12])}")
    lines.append("")

    lines.append("三、职业探索与岗位匹配（人岗匹配度分析）")
    for i, m in enumerate(top_matches[:5], start=1):
        lines.append(f"{i}. {m.get('job_title')}（综合匹配度 {m.get('score')}%）")
        d4 = m.get("dimension_scores_4") or m.get("dimension_scores") or {}
        for d in MATCH_DIMENSIONS_4:
            if d in d4:
                lines.append(f"   - {d}：{d4[d]}%")
        gap = m.get("gap_analysis") or {}
        miss = gap.get("missing_skills") or []
        if miss:
            lines.append(f"   - 主要差距：{', '.join(miss[:6])}")
    lines.append("")

    lines.append("四、职业目标设定与职业路径规划")
    if top_matches:
        top = top_matches[0]
        lines.append(f"- 近期主攻方向：{top.get('job_title')}（结合个人意愿与市场需求）")
        lines.append("- 垂直晋升路径示例：实习/校招 → 初级岗位（0-2年）→ 中级（2-4年）→ 资深/小组长（4-6年）→ 负责人/专家")
        lines.append("- 换岗路径：同领域相近岗位可互相迁移（如数据分析↔商业分析↔产品分析）；技术岗可向产品/项目管理延伸。")
    lines.append("")

    lines.append("五、行动计划与成果展示（分阶段可执行）")
    lines.append("- 短期（1-2 周）：完善简历（JD 关键词+量化成果），整理 3 个 STAR 案例；选定 1 个目标岗位序列。")
    lines.append("- 中期（1-3 个月）：完成 1 个作品集项目（可部署/可复现），补齐缺失技能清单前 3 项；投递与复盘（每周 30-50 个），模拟面试 6-10 次。")
    lines.append("- 评估周期与指标：每 2 周复盘简历打开率与面试邀约；每月更新能力画像与匹配度；按季度调整目标岗位与学习路径。")
    lines.append("")

    lines.append("六、备注")
    lines.append("- 本报告基于当前简历/测评数据自动生成，扬长避短、精准匹配；补充经历与作品后可重新生成以提升准确率。")
    return "\n".join(lines)


def report_completeness_check(content: str) -> dict[str, Any]:
    """报告内容完整性检查，返回缺失章节与建议。"""
    required = ["基本信息", "能力画像", "岗位匹配", "职业目标", "路径", "行动计划", "评估"]
    missing = []
    for s in required:
        if s not in content:
            missing.append(s)
    return {"complete": len(missing) == 0, "missing_sections": missing}


@dataclass
class AIHelper:
    client: AIClient

    def parse_resume(self, resume_text: str, manual: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        manual = manual or {}
        system = "你是职业规划助手，从简历中抽取结构化就业能力画像。画像须包含：专业技能、证书、创新能力、学习能力、抗压能力、沟通能力、实习能力、团队协作、问题解决、职业稳定性；并给出完整度与竞争力评分(0-100)。"
        dims_str = ",".join([f'"{d}":0-100' for d in PROFILE_DIMENSIONS])
        schema = f'{{"major":"专业(可空)","skills":["技能"],"certs":["证书"],"internships":"实习摘要","highlights":["亮点"],"dimensions":{{{dims_str}}},"completeness_score":0-100,"competitiveness_score":0-100}}'
        prompt = f"请解析以下简历文本，并结合手动信息输出 JSON。\n\n【手动信息】{_safe_json_dumps(manual)}\n\n【简历文本】\n{resume_text[:8000]}"
        try:
            data = self.client.chat_json(system, prompt, schema_hint=schema)
            if isinstance(data, dict) and "skills" in data and "dimensions" in data:
                return data
        except Exception:
            pass
        return offline_parse_resume(resume_text, manual=manual)

    def generate_job_profile(self, job: dict[str, Any]) -> dict[str, Any]:
        system = "你是人岗匹配专家，将岗位JD抽象成不少于10维的岗位画像：专业技能、证书要求、创新能力、学习能力、抗压能力、沟通能力、实习能力、团队协作、问题解决、职业稳定性；每维0-100。"
        dims_str = ",".join([f'"{d}":0-100' for d in PROFILE_DIMENSIONS])
        schema = f'{{"title":"岗位名称","industry":"行业","key_skills":["核心技能"],"cert_requirements":["证书要求"],"dimensions":{{{dims_str}}},"summary":"画像描述"}}'
        prompt = f"根据岗位信息输出岗位画像JSON。\n\n{_safe_json_dumps(job)}"
        try:
            data = self.client.chat_json(system, prompt, schema_hint=schema)
            if isinstance(data, dict) and "key_skills" in data and "dimensions" in data:
                return data
        except Exception:
            pass
        return offline_generate_job_profile(job)

    def match(self, student_profile: dict[str, Any], job_profile: dict[str, Any]) -> dict[str, Any]:
        system = "你是人岗匹配模型。从基础要求、职业技能、职业素养、发展潜力四维度对比学生与岗位，输出每维得分(0-100)、综合加权得分、缺失技能与建议。"
        schema = '{"score":0-100,"dimension_scores":{},"dimension_scores_4":{"基础要求":0-100,"职业技能":0-100,"职业素养":0-100,"发展潜力":0-100},"gap_analysis":{"missing_skills":[],"suggestions":[]},"reasoning":"一句话"}'
        prompt = f"学生画像：{_safe_json_dumps(student_profile)}\n岗位画像：{_safe_json_dumps(job_profile)}\n请输出JSON。"
        try:
            data = self.client.chat_json(system, prompt, schema_hint=schema)
            if isinstance(data, dict) and "score" in data:
                return data
        except Exception:
            pass
        return offline_match(student_profile, job_profile)

    def generate_report(
        self, student: dict[str, Any], top_matches: list[dict[str, Any]], goal: str = ""
    ) -> str:
        system = "你是大学生职业规划顾问，输出结构化的职业规划报告（中文）。"
        prompt = f"学生信息：{_safe_json_dumps(student)}\n匹配结果TOP5：{_safe_json_dumps(top_matches[:5])}\n目标：{goal or ''}\n请输出一份可直接展示的报告正文。"
        try:
            data = self.client.chat_json(system, prompt, schema_hint="直接输出 {\"content\":\"...\"} 或纯文本")
            if isinstance(data, dict) and "content" in data and isinstance(data["content"], str):
                return data["content"]
        except Exception:
            pass
        return offline_generate_report(student, top_matches, goal=goal)

