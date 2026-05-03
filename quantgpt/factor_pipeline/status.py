"""模板对照 — 程序化实现矩阵（供报表 / 看板使用）。"""

from __future__ import annotations

from typing import Any

# status: "done" | "partial" | "planned" | "na"

IMPLEMENTATION_MATRIX: list[dict[str, Any]] = [
    {
        "id": "§6.1",
        "name": "锚因子提交",
        "status": "partial",
        "note": "REST 创建/列表/详情/PATCH；rationale≥50；reference_backtest；SeedFactorRevision；附件 URLs",
    },
    {
        "id": "§6.2",
        "name": "入库条件加载",
        "status": "partial",
        "note": "默认包 DEFAULT_RULE_BUNDLE + PipelineRuleProfile.rules_json 合并；REST CRUD；缺纯 UI 规则编辑器",
    },
    {
        "id": "§6.3",
        "name": "LLM 最小改动",
        "status": "partial",
        "note": "factor_pipeline.minimal_edit_generator + GenerationBatch；可选 FACTOR_PIPELINE_LLM_AUDIT→audit minimal_edit_llm_audit；缺统一 token 计量面板",
    },
    {
        "id": "§6.4",
        "name": "表达式门禁",
        "status": "partial",
        "note": "validate_wq + validate_wq_full；可选 FACTOR_PIPELINE_SEMANTIC_MVP / semantic_mvp 参数附加启发式；非完整语义 AST",
    },
    {
        "id": "§6.5",
        "name": "WQ 回测",
        "status": "partial",
        "note": "simulate→wq_simulation_runs；mock；simulate/gated + PipelineRunJob；POST run/complete（FACTOR_PIPELINE_ONE_CLICK）；门面 run_gate_simulate_decide；缺分布式队列",
    },
    {
        "id": "§6.6",
        "name": "评估与入库",
        "status": "partial",
        "note": "硬门槛+IR+OOS衰减+composite_score；rule_profile_id；human_review+approval_chain；去重仍为 stub",
    },
    {
        "id": "§6.7",
        "name": "审计输出",
        "status": "partial",
        "note": "AuditTrail；GET /audit/trails；GET /factor_pipeline/trace；缺合规导出包",
    },
    {"id": "§7.1", "name": "锚因子管理", "status": "partial", "note": "PATCH+修订表；缺 bulk 导入"},
    {"id": "§7.2", "name": "规则配置中心", "status": "partial", "note": "pipeline_rule_profiles + API；缺变更审计专用视图"},
    {"id": "§7.3", "name": "LLM 生成管理", "status": "partial", "note": "模型/温度/批次表；缺统一 token 计量面板"},
    {"id": "§7.4", "name": "表达式树门禁", "status": "partial", "note": "启发式复杂度+Parser；缺 AST 可视化与枚举化全套"},
    {"id": "§7.5", "name": "回测编排", "status": "partial", "note": "PipelineRunJob+gated；缺优先级/重试策略配置中心"},
    {"id": "§7.6", "name": "入库与审批", "status": "partial", "note": "人工审批链 API；多级审批策略仍为简化版"},
    {"id": "§7.7", "name": "审计追溯", "status": "partial", "note": "trace 聚合；缺生命周期导出与跨实体 JOIN 报表"},
    {"id": "§10", "name": "接口", "status": "partial", "note": "REST 扩展集+MCP；WQ/DeepSeek 现状"},
    {"id": "§11.2", "name": "综合评分", "status": "done", "note": "scoring.compute_composite_score；入库 reasons + DB 列"},
    {"id": "§13-15", "name": "监控与验收", "status": "planned", "note": "metrics/summary 轻量；Prometheus/告警见路线图 P2"},
]


def summarize_completion() -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in IMPLEMENTATION_MATRIX:
        s = row["status"]
        counts[s] = counts.get(s, 0) + 1
    return counts
