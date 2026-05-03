# LLM 因子研发改造方案 — 与本仓库 `quantgpt.factor_pipeline` 对照说明

本文档将《LLM 因子开发改造方案（模板版）》与当前代码库实现逐项对照。**结论先行：M1–M7 仅为 MVP，模板中大量「规则中心、多级审批、综合评分、审计看板、生产化编排」等尚未实现或仅为占位。**

---

## 1. 背景与目标

| 模板诉求 | 实现情况 |
|---------|---------|
| 可解释、可控、可审计闭环 | **部分**：锚因子必填 rationale、最小改动提示约束、审计事件 append-only |
| 经济学含义强约束 | **部分**：依赖人工锚因子 + LLM 最小改动文案约束；无独立「经济语义校验器」 |
| 降低无效候选 | **部分**：WQ 模式 Parser 门禁 + 可选标识符白名单；未做批量预筛队列 |
| 回测前强门禁 | **部分**：语法 + WQ 兼容门禁；**未**实现独立 AST 复杂度报表 |
| 入库标准化与追溯 | **部分**：`AdmissionDecision` + `AuditTrail`；无全流程聚合查询 API |

---

## 2. 适用范围（§3）

占位见 `factor_pipeline.config.DEFAULT_APPLICABILITY`，**不参与运行时校验**，由部署方填写文档/配置。

---

## 3. 术语与架构层（§4–§5）

逻辑七层在代码中的对应关系：

1. **锚因子输入** → `routes/seed_factors` + `SeedFactor`
2. **规则与门槛** → `factor_pipeline.config.DEFAULT_ADMISSION_THRESHOLDS`（硬编码占位，非规则中心）
3. **LLM 最小改动** → `minimal_edit_generator` + `GenerationBatch` / `EditCandidate`
4. **表达式门禁** → `expression_gate` + `ExpressionParser(mode="wq")`
5. **WQ 回测** → `wq_pipeline` + `WQSimulationRun`（`WQBrainClient.simulate`，支持 mock）
6. **入库决策** → `factor_pipeline.admission` + `AdmissionDecision`
7. **审计** → `audit_log` + `AuditTrail`

门面聚合类：`FactorResearchPipeline`（`quantgpt.factor_pipeline.facade`）。

---

## 4. 业务流程（§6）

| Step | 说明 | 实现 |
|------|------|------|
| 1 锚因子提交 | 表达式、economics、市场/池/频率、黑名单、附件 | **部分**：创建/列表/详情；**缺** PATCH 版本化、专用「参考回测」字段 |
| 2 入库条件加载 | 可配置门槛中心 | **占位**：`config.py` 常量；**缺** DB/API、灰度 |
| 3 LLM 最小改动 | 缺口指标 + 候选 + 改动说明 | **部分**：DeepSeek JSON、`prompt_version`/温度落库 |
| 4 表达式树合规 | 语法、白名单、复杂度、WQ 映射 | **部分**：Parser + tokenizer 白名单；**非**独立 AST 树；复杂度沿用 Parser 内置上限 |
| 5 WQ 回测 | 仅 PASS 候选 | **未严格耦合**：路由侧未强制「先门禁再 simulate」；脚本可自行编排。simulate 轮询/重试在 `WQBrainClient` |
| 6 评估入库 | 硬门槛、评分、去重、人工 | **部分**：Sharpe/Fitness/Turnover 硬门槛；**缺** IR/样本外衰减、加权 Score、多级审批、真实相关性去重（stub） |
| 7 输出与审计 | 清单、结论、链路 | **部分**：REST 返回 + `AuditTrail`；**缺** 按因子 ID 一键追溯接口 |

---

## 5. 功能需求（§7）

| 小节 | 状态 |
|------|------|
| 7.1 锚因子版本化/编辑 | **缺** |
| 7.2 规则配置中心 | **缺**（仅占位 config） |
| 7.3 LLM 生成管理 | **部分**（env + 批次表） |
| 7.4 表达式树门禁 | **部分**（静态校验；无可视化树） |
| 7.5 回测编排 | **部分**（单请求；无流水线任务表） |
| 7.6 入库审批 | **缺**人工/多级；仅有自动规则 |
| 7.7 审计追溯查询 | **缺**聚合查询 |

---

## 6. 非功能需求（§8）

未系统性验收；密钥依赖 `.env`（参见项目既有实践）。

---

## 7. 接口（§10）

| 类型 | 实现 |
|------|------|
| LLM | DeepSeek Chat Completions（`deepseek_client` / `minimal_edit_generator`） |
| WorldQuant | `WQBrainClient.simulate`；REST `POST /api/v1/wq_simulations/run` |
| 内部 | `validate_wq`、`admission/decide`、审计写入；MCP：`validate_wq_gate`、`wq_pipeline_simulate`、`evaluate_admission_rules` |

---

## 8. 评分与标准（§11）

- **11.1 硬门槛**：部分覆盖（Sharpe、Fitness、Turnover），参数见 `DEFAULT_ADMISSION_THRESHOLDS`。
- **11.2 综合加权 Score**：**未实现**。

---

## 9. 风险与监控（§12–§13）

缓解措施仅部分体现在产品设计（最小改动、门禁、mock）；**无**独立监控指标采集服务。

---

## 10. 里程碑（§14）对照

- **M1 MVP**：锚因子、最小改动、门禁、WQ 单路径 simulate、基础入库规则、审计事件 — **基本完成（简化版）**。
- **M2/M3**：模板所列增强与生产化 — **未在本仓库范围实现**。

---

## 11. 程序化矩阵

运行时可导入：

```python
from quantgpt.factor_pipeline import IMPLEMENTATION_MATRIX, summarize_completion
```

---

## 12. 代码入口

- 包根：`quantgpt/factor_pipeline/`
- 门面：`FactorResearchPipeline`（`from quantgpt.factor_pipeline import FactorResearchPipeline`）
- 向后兼容：`quantgpt.admission_rules` 仍 re-export 入库函数
