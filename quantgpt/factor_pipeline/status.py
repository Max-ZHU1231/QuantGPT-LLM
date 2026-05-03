"""模板对照 — 程序化实现矩阵（供报表 / 看板使用）。"""

from __future__ import annotations

from typing import Any

# status: "done" | "partial" | "planned" | "na"

IMPLEMENTATION_MATRIX: list[dict[str, Any]] = [
    {"id": "§6.1", "name": "锚因子提交", "status": "partial", "note": "REST 创建/列表/详情；经济学 rationale≥50；附件 URLs；缺 PATCH 版本化"},
    {"id": "§6.2", "name": "入库条件加载", "status": "partial", "note": "硬门槛在 config.DEFAULT_ADMISSION_THRESHOLDS；缺规则中心 API / 灰度"},
    {"id": "§6.3", "name": "LLM 最小改动", "status": "partial", "note": "DeepSeek + GenerationBatch/EditCandidate；prompt_version 落库；缺前端可调候选数上限"},
    {"id": "§6.4", "name": "表达式门禁", "status": "partial", "note": "WQ 模式 Parser + 可选标识符白名单；非 AST 树可视化；复杂度沿用 Parser 内置 MAX_DEPTH 等"},
    {"id": "§6.5", "name": "WQ 回测", "status": "partial", "note": "simulate→wq_simulation_runs；mock；WQBrainClient 自带轮询重试；缺流水线专属队列/优先级"},
    {"id": "§6.6", "name": "评估与入库", "status": "partial", "note": "AdmissionDecision + 规则引擎；缺多级审批、综合加权评分、真实去重"},
    {"id": "§6.7", "name": "审计输出", "status": "partial", "note": "AuditTrail 关键事件；缺按因子 ID 聚合查询 API / 看板"},
    {"id": "§7.1", "name": "锚因子管理", "status": "partial", "note": "缺编辑/版本历史表"},
    {"id": "§7.2", "name": "规则配置中心", "status": "planned", "note": "占位 config.py"},
    {"id": "§7.3", "name": "LLM 生成管理", "status": "partial", "note": "模型/温度 env；批次表记录"},
    {"id": "§7.4", "name": "表达式树门禁", "status": "partial", "note": "静态校验为主；缺树可视化与失败分类枚举"},
    {"id": "§7.5", "name": "回测编排", "status": "partial", "note": "单请求同步 simulate；缺编排状态机表"},
    {"id": "§7.6", "name": "入库与审批", "status": "partial", "note": "自动决策 only；缺人工审批流 / 标签库"},
    {"id": "§7.7", "name": "审计追溯", "status": "partial", "note": "append-only 事件；缺追溯查询"},
    {"id": "§10", "name": "接口", "status": "partial", "note": "REST+MCP 子集；LLM 走 DeepSeek；WQ 走现有 Client"},
    {"id": "§11.2", "name": "综合评分", "status": "planned", "note": "未实现加权 Score"},
    {"id": "§13-15", "name": "监控与验收", "status": "planned", "note": "依赖运营接入"},
]


def summarize_completion() -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in IMPLEMENTATION_MATRIX:
        s = row["status"]
        counts[s] = counts.get(s, 0) + 1
    return counts
