"""Minimal-edit candidate generation via DeepSeek (OpenAI-compatible Chat API)."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import uuid
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .deepseek_client import chat_completion, factor_llm_client, factor_llm_config
from .expression_parser import __doc__ as _expr_module_doc
from .llm_service import OPERATORS_DOC
from .managers.seed_factor_manager import SeedFactorManager
from .seed_models import EditCandidate, GenerationBatch, SeedFactor

logger = logging.getLogger(__name__)

_OPERATORS_DOC = (_expr_module_doc or "").strip() or OPERATORS_DOC

_MINIMAL_EDIT_RULES = """
================================================================================
任务：最小改动模式（Seed Factor → 候选表达式）
================================================================================
- 你必须以「锚定因子表达式」为起点，只做**最小必要**的改动（参数微调、增减一层 rank/ts_*、
  与其它已允许字段的温和组合等），禁止完全重写为 unrelated 的新因子故事。
- 每个候选必须是**单行**、可直接交给 QuantGPT 解析器执行的表达式。
- 严禁 markdown、代码块、反引号、解释性前言或「根据分析」类废话。
- 生成 **2～5** 个候选；优先多样化小幅改动而非同质化堆叠。
- 遵守锚定因子自带的 blacklist_operators / blacklist_fields（用户消息中会列出）。
- 输出必须是 **单个合法 JSON 对象**（不要 JSON 以外的任何字符）。

JSON 格式（严格遵守键名）：
{
  "candidates": [
    {
      "expression": "单行因子表达式",
      "edit_summary": {
        "edit_direction": "conservative | aggressive | reinforcement",
        "edits": [
          {"type": "param_tuning | operator_swap | composition | other", "detail": "简述改了什么"}
        ]
      },
      "expected_impact": {
        "sharpe_delta": "例如 +0.05~0.12",
        "ic_delta": "可选字符串",
        "turnover_delta": "可选字符串",
        "confidence": "low | medium | high"
      },
      "core_logic_preserved": true,
      "deviation_explanation": null
    }
  ]
}
================================================================================
"""


def _minimal_edit_system_prompt() -> str:
    return _MINIMAL_EDIT_RULES + "\n\n" + _OPERATORS_DOC


def _build_user_prompt(
    seed: SeedFactor,
    target_gap: dict,
    knowledge_base: dict | None,
) -> str:
    kb = knowledge_base or {}
    verified = kb.get("verified_rules") or []
    failed = kb.get("failed_paths") or []
    parts = [
        "=== 锚定种子因子 ===",
        f"id: {seed.id}",
        f"name: {seed.name}",
        f"expression: {seed.expression}",
        f"econ_rationale: {seed.econ_rationale}",
        f"market: {seed.market}, universe: {seed.universe}, frequency: {seed.frequency}",
        f"factor_type: {seed.factor_type or ''}",
        f"blacklist_operators: {seed.blacklist_operators or []}",
        f"blacklist_fields: {seed.blacklist_fields or []}",
        "",
        "=== 改动目标（数值缺口）===",
        f"metric: {target_gap.get('metric', '')}",
        f"current: {target_gap.get('current')}",
        f"target: {target_gap.get('target')}",
        f"constraint: {target_gap.get('constraint', '')}",
        "",
        "=== 知识库（可选）===",
        f"verified_rules: {json.dumps(verified, ensure_ascii=False)}",
        f"failed_paths: {json.dumps(failed, ensure_ascii=False)}",
        "",
        "请输出 JSON（仅 JSON）。",
    ]
    return "\n".join(parts)


def _deepseek_chat(messages: list[dict[str, str]]) -> str:
    cfg = factor_llm_config()
    client = factor_llm_client()
    resp = chat_completion(
        client,
        model=cfg["model"],
        messages=messages,
        temperature=0.3,
        max_tokens=int(os.environ.get("DEEPSEEK_MAX_TOKENS", "8192")),
        timeout=int(os.environ.get("DEEPSEEK_TIMEOUT", "120")),
    )
    text = (resp.choices[0].message.content or "").strip()
    if not text:
        raise RuntimeError(
            "DeepSeek 返回空内容；可提高 DEEPSEEK_MAX_TOKENS 或改用 deepseek-chat。"
        )
    return text


def _extract_json_object(raw: str) -> dict:
    raw = raw.strip()
    m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", raw, re.IGNORECASE)
    if m:
        raw = m.group(1).strip()
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("LLM JSON 根节点必须是对象")
    return data


def _parse_candidates_payload(raw: str) -> list[dict]:
    data = _extract_json_object(raw)
    cands = data.get("candidates")
    if not isinstance(cands, list) or not cands:
        raise ValueError("JSON 缺少非空 candidates 数组")
    out: list[dict] = []
    for item in cands[:10]:
        if not isinstance(item, dict):
            continue
        expr = (item.get("expression") or "").strip()
        if "\n" in expr:
            expr = expr.split("\n")[-1].strip()
        expr = expr.strip("`").strip()
        if not expr:
            continue
        out.append(item)
    if not out:
        raise ValueError("没有可用的候选表达式")
    return out


def _new_batch_id() -> str:
    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    return f"batch_{day}_{uuid.uuid4().hex[:8]}"


def _new_candidate_id() -> str:
    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    return f"cand_{day}_{uuid.uuid4().hex[:8]}"


def _candidate_row(batch_id: str, seed_id: str, item: dict) -> EditCandidate:
    edit_summary = item.get("edit_summary")
    if not isinstance(edit_summary, dict):
        edit_summary = {"edits": [], "edit_direction": ""}
    edits = edit_summary.get("edits") if isinstance(edit_summary.get("edits"), list) else []
    exp_imp = item.get("expected_impact") if isinstance(item.get("expected_impact"), dict) else {}

    return EditCandidate(
        id=_new_candidate_id(),
        batch_id=batch_id,
        seed_factor_id=seed_id,
        expression=item["expression"].strip(),
        edit_summary=edit_summary,
        total_edits=len(edits),
        edit_direction=str(edit_summary.get("edit_direction") or "")[:50] or None,
        expected_sharpe_delta=str(exp_imp.get("sharpe_delta") or "")[:50] or None,
        expected_ic_delta=str(exp_imp.get("ic_delta") or "")[:50] or None,
        expected_turnover_delta=str(exp_imp.get("turnover_delta") or "")[:50] or None,
        impact_confidence=str(exp_imp.get("confidence") or "")[:50] or None,
        core_logic_preserved=bool(item.get("core_logic_preserved", True)),
        deviation_explanation=(str(item["deviation_explanation"])[:2000] if item.get("deviation_explanation") else None),
        created_at=datetime.now(timezone.utc),
    )


async def generate_minimal_edits_for_seed(
    db: AsyncSession,
    *,
    user_id: UUID,
    seed_factor_id: str,
    target_gap: dict,
    knowledge_base: dict | None = None,
) -> GenerationBatch:
    """Load owned seed factor, call DeepSeek, persist batch + candidates (or failed batch)."""
    mgr = SeedFactorManager(db)
    seed = await mgr.get_owned(user_id=user_id, seed_factor_id=seed_factor_id)
    if not seed:
        raise ValueError("SEED_NOT_FOUND")

    cfg = factor_llm_config()
    if not (cfg.get("api_key") or "").strip():
        raise RuntimeError("DEEPSEEK_API_KEY_NOT_SET")

    now = datetime.now(timezone.utc)
    batch = GenerationBatch(
        id=_new_batch_id(),
        seed_factor_id=seed.id,
        model=cfg["model"],
        temperature=0.3,
        prompt_version="m1-3-v1",
        target_metric=str(target_gap.get("metric") or "")[:50] or None,
        current_value=target_gap.get("current") if isinstance(target_gap.get("current"), (int, float)) else None,
        target_value=target_gap.get("target") if isinstance(target_gap.get("target"), (int, float)) else None,
        constraint_description=(str(target_gap.get("constraint") or "")[:4000] or None),
        knowledge_base_snapshot=knowledge_base,
        candidate_count=0,
        generation_status="running",
        created_at=now,
    )
    db.add(batch)
    await db.flush()

    try:
        system = _minimal_edit_system_prompt()
        user_msg = _build_user_prompt(seed, target_gap, knowledge_base)
        messages: list[dict[str, str]] = [
            {"role": "system", "content": system},
            {"role": "user", "content": user_msg},
        ]
        raw = await asyncio.to_thread(_deepseek_chat, messages)
        items = _parse_candidates_payload(raw)
        for item in items:
            db.add(_candidate_row(batch.id, seed.id, item))
        batch.candidate_count = len(items)
        batch.generation_status = "completed"
        batch.completed_at = datetime.now(timezone.utc)
    except Exception as e:
        logger.warning("minimal edit generation failed: %s", e)
        batch.generation_status = "failed"
        batch.error_message = str(e)[:4000]
        batch.completed_at = datetime.now(timezone.utc)

    return batch


async def get_batch_for_user(
    db: AsyncSession,
    *,
    user_id: UUID,
    batch_id: str,
) -> tuple[GenerationBatch, list[EditCandidate]] | None:
    """Return batch + candidates if the batch's seed factor belongs to user."""
    res = await db.execute(select(GenerationBatch).where(GenerationBatch.id == batch_id))
    batch = res.scalar_one_or_none()
    if not batch:
        return None

    mgr = SeedFactorManager(db)
    seed = await mgr.get_owned(user_id=user_id, seed_factor_id=batch.seed_factor_id)
    if not seed:
        return None

    rc = await db.execute(select(EditCandidate).where(EditCandidate.batch_id == batch_id))
    cands = list(rc.scalars().all())
    return batch, cands
