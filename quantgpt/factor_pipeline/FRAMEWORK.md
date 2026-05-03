# LLM 因子研发流水线 — 模板对照与实现说明

本文档将《LLM 因子开发改造方案（模板版）》与当前 **`quantgpt.factor_pipeline`** 及关联路由/表结构对齐。**结论**：M1 锚定→最小改动→门禁→simulate→入库→审计 **已形成可运行闭环**；规则画像、综合分、溯源接口、门禁编排（含 **`PipelineRunJob`**）、**可选一键** gate→simulate→decide、人工审批一期等 **已实现**。**可选**：环境变量开启语义启发式（`semantic_mvp.py`）、最小改动 LLM 审计、Prometheus 钩子占位。模板中的「完整语义 AST 校验、统计相关去重、生产级 Prometheus 告警」等仍为 **规划或占位**。

**包版本**：`PIPELINE_VERSION`（见 `quantgpt/factor_pipeline/__init__.py`），当前为 **`1.3.0-mvp`**。

---

## 1. 背景与目标

| 模板诉求 | 实现情况 |
|---------|---------|
| 可解释、可控、可审计闭环 | **较好**：锚因子 rationale、最小改动强约束提示词（`minimal_edit_generator`）、append-only 审计 + `trace` 聚合 |
| 经济学含义强约束 | **部分**：依赖锚文案 + LLM 最小改动规则；可选 **`FACTOR_PIPELINE_SEMANTIC_MVP`** 附加 **`semantic_mvp`** 启发式（非 AST）；**无**独立非 LLM「经济语义校验器」 |
| 降低无效候选 | **部分**：WQ Parser、`validate_wq_full`（失败分类/复杂度启发式）、可选白名单；无批量预筛队列 |
| 回测前强门禁 | **部分**：语法 + 长度/嵌套；**非**独立「泄漏检测 AST」 |
| 入库标准化与追溯 | **较好**：`AdmissionDecision`（含 composite、人工字段）、`GET .../trace/{seed_factor_id}`、`GET .../audit/trails` |

---

## 2. 适用范围（§3）

占位仍见 `factor_pipeline.config.DEFAULT_APPLICABILITY`，**不参与运行时强制校验**，由部署方在文档/环境中约定。

---

## 3. 术语与架构层（§4–§5）

| 层 | 代码入口 |
|----|-----------|
| 1 锚因子 | `routes/seed_factors` · `SeedFactor`（`seed_models`）· `SeedFactorManager`（创建 / PATCH / `SeedFactorRevision`） |
| 2 规则与画像 | `PipelineRuleProfile` · `rule_merge.merge_rule_bundle` · REST `/api/v1/factor_pipeline/rules/profiles` |
| 3 LLM 最小改动 | **`factor_pipeline.minimal_edit_generator`** · **`factor_pipeline.minimal_edits_routes`** · `GenerationBatch` / `EditCandidate` · **`/api/v1/minimal_edits/*`** |
| 4 表达式门禁 | `expression_gate.validate_wq` · **`validate_wq_full`**（可选 **`semantic_mvp`** 参数或 **`FACTOR_PIPELINE_SEMANTIC_MVP`**）· REST `/api/v1/expressions/validate_wq(_full)` |
| 5 WQ simulate | `wq_pipeline` · `WQSimulationRun` · `/api/v1/wq_simulations/run` · **`gated_run.run_gated_wq_pipeline`** → **`/api/v1/factor_pipeline/simulate/gated`**（`PipelineRunJob`） |
| 5b 一键编排（可选） | **`orchestration.run_gate_simulate_decide`** · **`POST /api/v1/factor_pipeline/run/complete`**（需 **`FACTOR_PIPELINE_ONE_CLICK`**）· 门面 **`FactorResearchPipeline.run_gate_simulate_decide`** |
| 6 入库 | `factor_pipeline.admission` · **`admission_persist.persist_admission_decision_for_run`** · `AdmissionDecision` · `/api/v1/admission/decide` · **`human_review`** |
| 7 审计 | `audit_log` · `AuditTrail` · **`/api/v1/audit/trails`** |

门面：`FactorResearchPipeline`（`quantgpt.factor_pipeline.facade`）。

数据库：**Alembic `015`** — `reference_backtest`、`seed_factor_revisions`、`pipeline_rule_profiles`、`pipeline_run_jobs`、`admission_decisions` 扩展列等（见 `quantgpt/migrations/versions/015_factor_pipeline_extensions.py`）。种子侧 ORM 使用 **`Mapped` / `mapped_column`**（`seed_models.py`），便于静态类型检查。

---

## 4. 业务流程（§6）

| Step | 说明 | 实现 |
|------|------|------|
| 1 锚因子 | 表达式、economics、市场/池/频率、黑名单、`reference_backtest`、附件 | **REST**：`POST/GET/PATCH /api/v1/seed_factors`；PATCH 写 **`SeedFactorRevision`** |
| 2 规则加载 | 正式/灰度画像 | **`PipelineRuleProfile.rules_json`** 合并默认包 **`DEFAULT_RULE_BUNDLE`**（`rule_merge.py`） |
| 3 LLM 最小改动 | 缺口 + 候选 JSON | **DeepSeek**（`factor_pipeline.minimal_edit_generator`）；`prompt_version`（如 **`m1-3-v2-en-minimal`**）；温度落库；支持空 **`candidates`**；可选 **`FACTOR_PIPELINE_LLM_AUDIT`** → 审计事件 **`minimal_edit_llm_audit`** |
| 4 门禁 | 语法、白名单、复杂度 | **`validate_wq_full`**（失败分类、`complexity`、`repair_hints`）；可选 **`semantic_mvp`** 附加字段（**不单独推翻** parser `valid`） |
| 5 WQ simulate | 门禁通过后 simulate | **任选**：`/wq_simulations/run` · **`simulate/gated`** · 或 **`run/complete`**（门禁→simulate→**自动 decide**，见特性开关） |
| 6 评估入库 | 门槛 + 综合分 + 人工 | **门槛**：Sharpe/Fitness/Turnover；可选 **IR**、**OOS Sharpe 衰减**（画像）；**`compute_composite_score`**；**`requires_human_review`**；**`correlation_dedup_stub`**（占位） |
| 7 审计 | 事件 + 溯源 | **`write_audit_event`**；**`GET /factor_pipeline/trace/{id}`**；**`GET /audit/trails`**；一键成功路径可写 **`pipeline_validation_bundle`** / **`pipeline_one_click_complete`** |

---

## 5. 功能需求（§7）

| 小节 | 状态 |
|------|------|
| 7.1 锚因子版本化 | **已实现**：PATCH + `seed_factor_revisions` |
| 7.2 规则配置中心 | **已实现**：`pipeline_rule_profiles` + CRUD REST |
| 7.3 LLM 生成管理 | **部分**：`minimal_edit_generator` + 批次表；可选审计开关；缺统一 token 计量面板 |
| 7.4 表达式门禁 | **部分**：Parser + **`validate_wq_full`** + **`semantic_mvp`**（启发式）；**非** WQ 完整 AST 语义树 |
| 7.5 回测编排 | **部分**：**`gated_run`** + **`PipelineRunJob`** + gated simulate；**`run/complete`**（特性开关）；缺优先级队列/多租户隔离 |
| 7.6 入库审批 | **部分**：**人工审批链** `approval_chain`、`human_review` API；多级策略仍简化为链上规则 |
| 7.7 审计追溯 | **已实现**：trace + audit/trails；一键路径附带校验快照审计；缺导出 HTML/CSV 合规包 |

---

## 6. 非功能需求（§8）

密钥与 BRAIN：`WQ_BRAIN_EMAIL` / `WQ_BRAIN_PASSWORD`；开发可用 **`WQ_SIMULATE_MOCK`** 或请求级 **`mock`**。

**因子流水线特性开关**（`factor_pipeline/feature_flags.py`，默认关闭）：

| 变量 | 含义 |
|------|------|
| **`FACTOR_PIPELINE_ONE_CLICK`** | 启用 **`POST /api/v1/factor_pipeline/run/complete`** |
| **`FACTOR_PIPELINE_LLM_AUDIT`** | 最小改动成功后写 **`minimal_edit_llm_audit`** |
| **`FACTOR_PIPELINE_SEMANTIC_MVP`** | **`validate_wq_full`** 默认附带 **`semantic_mvp`** |
| **`FACTOR_PIPELINE_PROMETHEUS`** | **`metrics_hook`** 占位（未注册真实 histogram） |

未接入独立 SIEM / 生产级 Prometheus（见路线图 P2）。

---

## 7. 接口（§10）

| 类型 | 路径 / 说明 |
|------|-------------|
| LLM | DeepSeek（**`factor_pipeline.minimal_edit_generator`** · `deepseek_client`） |
| WorldQuant | `WQBrainClient.simulate` · `POST /api/v1/wq_simulations/run` · **`POST /api/v1/factor_pipeline/simulate/gated`** |
| 一键流水线 | **`POST /api/v1/factor_pipeline/run/complete`**（同 gated 请求体 + 可选 **`rule_profile_id`**；需 **`FACTOR_PIPELINE_ONE_CLICK`**，否则 403） |
| 门禁 | `POST /api/v1/expressions/validate_wq` · **`validate_wq_full`** |
| 锚因子 | **`PATCH /api/v1/seed_factors/{id}`** |
| 最小改动 | **`POST /api/v1/minimal_edits/generate`** · **`GET /api/v1/minimal_edits/batches/{batch_id}`**（路由实现在 **`factor_pipeline/minimal_edits_routes.py`**） |
| 规则画像 | **`/api/v1/factor_pipeline/rules/profiles`** |
| 溯源 | **`GET /api/v1/factor_pipeline/trace/{seed_factor_id}`** |
| 指标 | **`GET /api/v1/factor_pipeline/metrics/summary`** |
| 审计列表 | **`GET /api/v1/audit/trails`** |
| 入库 | **`POST /api/v1/admission/decide`**（可选 **`rule_profile_id`**）· **`POST .../decisions/{id}/human_review`** |
| MCP | **`evaluate_admission_rules`**（可选 OOS、profile JSON）· `validate_wq_gate` · `wq_pipeline_simulate` |

---

## 8. 评分与标准（§11）

- **11.1 硬门槛**：Sharpe / Fitness / Turnover；画像可覆盖 **IR**、**OOS 衰减比**（`admission.py` + `scoring.py` / `rule_merge.py`）。
- **11.2 综合加权**：**已实现** **`compute_composite_score`**，结果写入 **`AdmissionDecision.composite_score`** 与 **`reasons`**。

---

## 9. 风险与监控（§12–§13）

缓解：最小改动约束、门禁 mock、人工审批可选链路。**轻量运维**：**`metrics/summary`** 窗口计数；一键成功可写 **`pipeline_validation_bundle`**。**`metrics_hook.py`** 为 P2 Prometheus 接入占位。**未**：告警规则、生产 histogram、异常检测自动化。

---

## 10. 里程碑（§14）

- **M1 MVP+**：锚因子 PATCH/修订、规则画像、扩展门禁、编排 Job、gated simulate、可选一键入库、入库画像+综合分+人工一期、trace/audit/metrics、最小改动迁入 **`factor_pipeline`** — **已达可用版本**。
- **M2+**：见下文 **P0/P1/P2 路线图**（结构化校验表、真实去重、观测平台等）。

---

## 11. 程序化矩阵

```python
from quantgpt.factor_pipeline import IMPLEMENTATION_MATRIX, summarize_completion
```

矩阵条目随版本迭代见 **`quantgpt/factor_pipeline/status.py`**。

附加惰性导出（可选）：**`generate_minimal_edits_for_seed`** · **`get_batch_for_user`**（见 **`__init__.py`**）。

---

## 12. 代码入口

- 包根：`quantgpt/factor_pipeline/`
- **核心模块**：`admission.py` · **`admission_persist.py`** · `rule_merge.py` · `scoring.py` · **`minimal_edit_generator.py`** · **`minimal_edits_routes.py`** · **`gated_run.py`** · **`orchestration.py`** · **`pipeline_dto.py`** · **`feature_flags.py`** · **`semantic_mvp.py`** · **`metrics_hook.py`** · `config.py` · `facade.py` · `status.py`
- **路由挂载**：`quantgpt/api_server.py` 注册 **`factor_pipeline`** 路由器与 **`minimal_edits_routes`**；另有 `routes/factor_pipeline.py` · `audit.py` · `admission.py` · `seed_factors.py` · `expression_gate.py`
- **兼容**：`quantgpt/minimal_edit_generator.py`（shim → **`factor_pipeline.minimal_edit_generator`**）
- 演示脚本：`scripts/demo_anchor_pipeline_once.py`（`--mock` · **`--random-factor`**）

---

## 13. 路线图（Copilot 方案压缩：P0 / P1 / P2）

> 来源：外部「增强流水线」设想，按依赖与收益压缩为三档；**非承诺排期**。已实现项在「说明」中标注 **✓**。

### P0 — 巩固闭环（1～2 周量级）

| 项 | 说明 |
|----|------|
| 文档与矩阵 | 保持 `FRAMEWORK.md` / `IMPLEMENTATION_MATRIX` 与代码同步 |
| 编排门面 | **✓** **`run_gate_simulate_decide`** · **`POST .../run/complete`** · **`FACTOR_PIPELINE_ONE_CLICK`** · **`facade`** |
| 迁移落地 | 生产环境执行 **015**；SQLite 开发库避免仅 `create_all` 导致缺列 |
| 最小改动观测 | **✓** **`FACTOR_PIPELINE_LLM_AUDIT`** → **`minimal_edit_llm_audit`** |

### P1 — 质量与数据（3～6 周量级）

| 项 | 说明 |
|----|------|
| 语义/经济校验 **MVP** | **部分 ✓**：**`semantic_mvp.py`** + **`validate_wq_full`**；可选 **二次 LLM judge** 仍未接 |
| 复杂度 **增强** | 在 Parser 可得的结构上加深（仍非完整远程 AST） |
| 校验/评分 **结构化落库** | **部分**：审计事件 **`pipeline_validation_bundle`**；独立 **`validation_records`** / **`scoring_records`** 表仍缺 |
| 真实相关去重 **v1** | 需因子收益序列：Spearman/皮尔逊 + 结构相似度；embedding 可选 |

### P2 — 平台化（6～11 周+）

| 项 | 说明 |
|----|------|
| 持久化知识库 | `KnowledgeBaseEntry`、成功/失败路径自动回流 |
| OOS 根因 **启发式/模型** | 过拟合 vs 制度切换 vs 漂移（需更多序列与市场上下文） |
| 可观测性 | **`metrics_hook`** 接入 **`prometheus_client`**、告警、生成延迟 histogram |
| 反馈闭环 | 用户 adopt/reject → 报表 → 提示词/画像迭代 |

---

**维护**：本文件应在变更 `factor_pipeline`、相关路由、**`015`** 后继迁移或 **`PIPELINE_VERSION`** 语义变更时同步修订。
