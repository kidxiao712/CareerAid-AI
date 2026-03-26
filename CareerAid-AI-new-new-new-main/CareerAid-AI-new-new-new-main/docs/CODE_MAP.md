# 代码修改位置说明

本文档说明各功能在哪个文件的哪个位置实现

---

## 1) 性格测试扩展（职业兴趣 + 可利用资源）

**文件**：`test.html`

- **职业兴趣区块**：约 156–164 行，新增 `#careerInterest` 容器，渲染 `CAREER_OPTIONS`（Java 开发、前端、AI/算法、大数据、测试、产品、项目管理），勾选 + 兴趣程度（非常/比较/一般）
- **可利用资源区块**：约 166–173 行，`#resources` 容器，渲染 `RESOURCE_OPTIONS`（家庭行业资源、校内导师、实习内推）+ 其他资源输入框
- **JS 逻辑**：`CAREER_OPTIONS`、`RESOURCE_OPTIONS` 常量，`renderCareerInterest()`、`renderResources()`、`collectCareerInterest()`、`collectResources()`，以及提交时把 `career_interest`、`resources` 加入 payload

---

## 2) 性格分析 Prompt + 短板诊断

**文件**：`ai_helper.py`

- **`offline_personality_analysis()`**：约 264–345 行，离线规则版性格分析；输入 `resume_profile`、`personality_test`，输出 `shortcomings`、`suggestions`、`job_fit`、`summary`
- **`AIHelper.analyze_personality_for_jobs()`**：约 413–433 行，优先调 LLM，失败时调用 `offline_personality_analysis`

**文件**：`docs/PROMPTS.md`

- **3.5) 性格分析 Prompt**：新增一节，明确性格分析 + 岗位适配 + 短板诊断的 system/user 与输出格式

---

## 3) 轻量级记忆模块（上下文联系）

**文件**：`context_memory.py`（新建）

- 全文件：内存 dict 按 `student_id` 存储 `profile_summary`、`key_facts`、`personality_diagnosis`、`regret_result`
- `set_profile_summary()`、`add_key_fact()`、`set_personality_diagnosis()`、`set_regret_result()`、`to_context_string()` 等

**文件**：`routes.py`

- **upload_resume**：约 193 行，`set_profile_summary(student.id, summary)` 写入画像摘要
- **submit_test**：约 212–219 行，`set_personality_diagnosis(student.id, diag)` 写入性格诊断
- **chat_send**：  
  - 约 484–489 行，`add_key_fact()` 从用户消息提取关键信息  
  - 约 491–507 行，构建 `combined` 并调用 `regret_matching_from_profile()`，`set_regret_result()`  
  - 约 512、529–533 行，用 `to_context_string()` 和 `regret_block` 注入 prompt

---

## 4) Regret Matching 博弈算法（多路径）

**文件**：`game_theory.py`

- **`regret_matching()`**：约 30–80 行，按 grade_level、introversion、risk_tolerance、family_support 计算 7 条路径（大厂高薪、高成长小厂/初创、国企稳定、体制内/公务员、保研/考研、自由职业/远程、出国深造/海外工作）的效用与后悔值，返回 `RegretResult(utils, regrets, best_action, recommendation, weights)`
- **`regret_matching_from_profile()`**：约 90–130 行，从 `profile`（dimensions + personality + career_interest + resources + constraints + user_prefs）抽取参数并调用 `regret_matching()`，用兴趣/资源/约束/即时偏好（更想稳定/不想出国）对 grade_level、risk_tolerance、family_support 做微调

**文件**：`docs/ALGORITHM.md`

- **第 6 节**：说明 7 条路径与参数含义，并指向 `game_theory.py`

---

## 5) Agent 情绪价值 + 博弈结果综合建议

**文件**：`routes.py`

- **chat_send** 中 `system_prompt`：约 510–517 行，改为“温暖、专业、有共情”的语气，并要求结合【性格与短板诊断】【博弈路径建议】
- **user_prompt**：约 529–536 行，注入 `memory_block`、`regret_block`，并说明要结合记忆、性格诊断、博弈路径、对话历史回答

---

## 6) 本地轻量 RAG 知识库

**文件**：`data/knowledge_career.md`

- 主流岗位能力要求、竞赛/证书含金量、典型职业路径节奏整理

**文件**：`knowledge.py`

- `search_knowledge(query, max_chunks)`：读取 `knowledge_career.md`，按关键字返回若干段落，供 Agent 作为“本地知识库参考”

**文件**：`routes.py`

- `chat_send` 内：约 541–548 行，调用 `search_knowledge(user_text)`，将结果拼入 `search_block`（【本地知识库参考】）一并注入大模型

---

## 7) 调用关系速查

```
test.html (提交)
  → POST /submit_test
    → routes.submit_test
      → ai.analyze_personality_for_jobs (ai_helper)
      → context_memory.set_personality_diagnosis

chat.html (发送)
  → POST /chat/send
    → routes.chat_send
      → context_memory.add_key_fact
      → game_theory.regret_matching_from_profile
      → context_memory.set_regret_result
      → to_context_string (拼记忆)
      → client.chat_text (带 memory + regret 的 prompt)
```
