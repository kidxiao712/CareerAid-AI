# 基于AI的大学生职业规划智能体（CareerAid AI）

本项目实现**任务要求**中的完整能力：**前端 9 页 + Flask + SQLite + 大模型（含火山引擎 API 预留）+ 企业 XLS 岗位数据导入**。

- **就业岗位要求画像**：不少于 10 维（专业技能、证书要求、创新能力、学习能力、抗压能力、沟通能力、实习能力、团队协作、问题解决、职业稳定性）；**岗位关联图谱**（垂直晋升 + 换岗路径，至少 5 个岗位族、每族不少于 2 条换岗路径）。
- **学生就业能力画像**：简历/手动录入 → 大模型拆解为 10 维能力画像 + 完整度/竞争力评分。
- **人岗匹配**：从**基础要求、职业技能、职业素养、发展潜力**四维度加权分析，关键技能匹配与维度契合度量化。
- **职业生涯发展报告**：职业探索与岗位匹配、职业目标与路径规划、分阶段行动计划与评估指标；支持完整性检查、一键导出。
- **大模型**：支持讯飞星火、OpenAI 兼容、**火山引擎（火山方舟/豆包）API 预留**；未配置时离线规则兜底。
- **企业数据**：支持 XLS/XLSX 导入（职位名称、工作地址、薪资范围、公司全称、所属行业、人员规模、企业性质、职位编码、职位描述、公司简介）。

---

## 目录结构

- 前端页面（项目根目录）
  - `index.html`
  - `login.html`
  - `chat.html`
  - `upload.html`
  - `test.html`
  - `job.html`
  - `match.html`
  - `map.html`
  - `report.html`
- 静态资源
  - `static/style.css`
  - `static/app.js`
- 后端（根目录 Python 文件）
  - `app.py`（Flask 入口）
  - `database.py`（数据库初始化）
  - `models.py`（ORM 模型：students/jobs/match_results/reports）
  - `routes.py`（API：/login /upload_resume /submit_test /jobs /match_jobs /generate_report）
  - `ai_client.py`（大模型客户端封装入口：可扩展星火/通用 OpenAI-兼容）
  - `ai_helper.py`（简历解析/岗位画像/匹配/报告：LLM 优先，失败自动回退）
- 数据导入与训练
  - `scripts/import_jobs.py`（导入岗位 CSV）
  - `ml/train_matcher.py`（可选训练）
  - `ml/matcher.py`（训练模型推理封装）
  - `requirements-ml.txt`
- 数据库文件（运行后生成）
  - `careeraid.db`

---

## 环境准备（Windows / PowerShell）

在项目根目录执行：

```bash
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

（可选）复制环境变量模板：

```bash
copy .env.example .env
```

---

## 启动后端并访问前端

```bash
python app.py
```

然后用浏览器打开：

- `http://127.0.0.1:5000/`

测试账号：

- 用户名：`admin`
- 密码：`123456`

---

## 核心接口（按需求定义）

- `POST /login`
- `POST /upload_resume`（multipart：`resume_file` + 手动字段）
- `POST /submit_test`（JSON）
- `GET /jobs`（支持 `?q=关键词`；额外支持 `include_match=1` 返回匹配预览）
- `POST /match_jobs`
- `POST /generate_report`（返回 `download_url`）

额外便捷接口（前端用来展示概览）：

- `GET /me`

---

## 导入企业岗位数据集

### CSV

列名建议：`title` / `industry` / `salary` / `requirements_text`。示例：`data/jobs_sample.csv`。

```bash
python scripts/import_jobs.py data/jobs_sample.csv
```

### 企业 XLS/XLSX（约 10000 条、100 岗位）

将企业提供的 **xls/xlsx** 放在项目下，列名支持：

- 职位名称、工作地址、薪资范围、公司全称、所属行业、人员规模、企业性质、职位编码、职位描述、公司简介

本项目企业数据文件路径示例：`20260226105856_457.xls`（项目根目录下）。

导入命令：

```bash
pip install openpyxl xlrd
python scripts/import_jobs_xls.py "20260226105856_457.xls"
# 或使用绝对路径：
# python scripts/import_jobs_xls.py "C:\Users\user\Desktop\CareerAid AI\20260226105856_457.xls"
```

导入后会自动生成 10 维岗位画像并写入数据库，刷新岗位列表与图谱即可使用。

---

## “训练”的脚手架（可选）

如果企业后续提供**标注好的人岗匹配数据**（例如：学生文本 + 岗位文本 + label），可使用 `ml/train_matcher.py` 训练一个可解释的监督模型：

安装训练依赖：

```bash
pip install -r requirements-ml.txt
```

训练数据格式（CSV 列）：

- `student_text`：学生技能+经历拼接文本
- `job_text`：岗位 JD 文本
- `label`：0/1（1=匹配）

训练并保存模型：

```bash
python ml/train_matcher.py data/labeled_pairs.csv ml/matcher.joblib
```

> 训练后的模型目前未自动接入后端匹配流程；企业落地时可将 `ai_helper.offline_match` 替换/融合为训练模型输出（并保留差距解释逻辑）。

---

## 大模型对接（星火 / 火山引擎 / 其他）

`ai_client.py` 支持：

- **火山引擎（火山方舟/豆包）**：`AI_PROVIDER=volc`，配置 `VOLC_BASE_URL`、`VOLC_API_KEY`、`VOLC_MODEL`。文档：https://www.volcengine.com/docs/82379/
- **OpenAI 兼容**：`AI_PROVIDER=openai_compatible`，配置 `OPENAI_BASE_URL`、`OPENAI_API_KEY`、`OPENAI_MODEL`
- **讯飞星火**：`AI_PROVIDER=spark`（占位，需按企业文档补齐鉴权）

未配置时自动回退 `offline`，项目可完整跑通。

