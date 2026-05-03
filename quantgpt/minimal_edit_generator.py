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
from .expression_gate import extract_identifier_tokens
from .managers.seed_factor_manager import SeedFactorManager
from .seed_models import EditCandidate, GenerationBatch, SeedFactor

logger = logging.getLogger(__name__)

_MINIMAL_EDIT_RULES = """
================================================================================
Task: Minimal Edit Mode (Seed Factor → Candidate Expressions)
================================================================================

[Core Objective]

You must use the user-provided Seed Factor expression as the ONLY starting point.

Your job is NOT to invent a brand-new factor.

Your job is to generate locally improved variants of the original factor while preserving its original economic meaning, signal intuition, and structural identity.

Think of this as:

Alpha Repair
Alpha Refinement
Local Search around existing alpha

NOT alpha reinvention.

================================================================================
I. Highest Priority Rules (Mandatory)
================================================================================

1. Preserve Core Logic

Every candidate must preserve:

- original alpha idea
- signal directionality
- economic rationale
- main operator structure

The result must still be recognizable as a natural variant of the seed factor.

Forbidden:

- unrelated new alpha story
- replacing momentum with value
- replacing mean reversion with volatility
- changing cross-sectional logic into time-series logic entirely
- full tree rewrite

-------------------------------------------------------------------------------

2. Only Minimal Edits Allowed

Each candidate may contain ONLY ONE of the following edit classes:

A. Operator Edit (exactly 1 place)

Replace one operator with a functionally nearby operator.

Examples:

ts_mean(x,20) → ts_decay_linear(x,20)
rank(x) → zscore(x)
ts_std_dev(x,20) → ts_zscore(x,20)
group_rank(x,g) → group_zscore(x,g)
add(x,y) → subtract(x,y)
divide(x,y) → multiply(x,inverse(y))

B. Parameter Edit (1–2 places max)

Adjust only parameters such as:

window length
lag
rate
std
constant
scale
threshold

Examples:

ts_mean(x,20) → ts_mean(x,15)
ts_rank(x,30) → ts_rank(x,45)
winsorize(x,std=4) → winsorize(x,std=3)
hump(x,0.01) → hump(x,0.02)

No large structural edits.

-------------------------------------------------------------------------------

3. No New Data Fields Allowed

You may ONLY use:

- fields explicitly provided by the user
- fields already appearing in the seed factor

Forbidden examples:

Seed uses close, volume
→ You may NOT add open/high/low/vwap

Seed uses returns
→ You may NOT add market_cap unless already provided

Zero tolerance for new fields.

-------------------------------------------------------------------------------

4. No Structural Rewrite

Forbidden:

- adding unrelated branches
- replacing whole formula tree
- introducing new factor combinations
- changing most nodes simultaneously
- adding 3+ new nested layers
- deleting main signal and keeping only wrappers

-------------------------------------------------------------------------------

5. Single-Line Executable Expression

Every candidate must be:

- one line only
- directly parsable by QuantGPT / WorldQuant style parser
- syntactically valid

-------------------------------------------------------------------------------

6. Output Format Restriction

Return ONE valid JSON object only.

No markdown.
No code block.
No commentary.
No explanation outside JSON.

================================================================================
II. Common WorldQuant Operators (Allowed ONLY as local edits)
================================================================================

[Arithmetic]

abs
add
subtract
multiply
divide
inverse
log
max
min
power
signed_power
sqrt
reverse
sign

[Logical]

and
or
not
if_else
<
<=
==
>
>=
!=
is_nan

[Time Series]

ts_delay
ts_delta
ts_mean
ts_sum
ts_std_dev
ts_zscore
ts_rank
ts_scale
ts_corr
ts_covariance
ts_decay_linear
ts_arg_max
ts_arg_min
ts_av_diff
ts_product
ts_quantile
ts_regression
days_from_last_change
hump
last_diff_value
kth_element
ts_backfill

[Cross Sectional]

rank
zscore
normalize
quantile
scale
winsorize

[Transformational]

bucket
trade_when

[Group]

group_rank
group_zscore
group_neutralize
group_scale
group_mean
group_backfill

[Vector] (only if vector field already exists)

vec_avg
vec_sum

================================================================================
III. Preferred Minimal Edit Patterns
================================================================================

1. Smoothing / Noise Reduction

ts_mean → ts_decay_linear
x → hump(x,0.01)

2. Robustness / Outlier Control

rank → zscore
x → winsorize(x,std=3)
ts_std_dev → ts_zscore

3. Window Tuning

5 ↔ 7 ↔ 10
10 ↔ 15 ↔ 20
20 ↔ 30 ↔ 40
60 ↔ 90

4. Lower Turnover

x → hump(x,0.01)
trade_when(cond,x,exit)

5. Group Neutral Improvement (only if group already exists)

group_rank → group_zscore
x → group_neutralize(x,industry)

================================================================================
IV. Forbidden Behavior
================================================================================

Do NOT:

- add new fields
- change multiple operators
- modify more than 2 params
- rewrite formula logic
- produce invalid syntax
- output markdown
- output comments
- output reasoning text

If no legal candidate exists:
return empty candidates array.

================================================================================
V. Optimization Goals
================================================================================

Candidates should ideally improve one or more:

- Sharpe
- IC
- Stability
- Turnover
- Robustness
- Neutralization quality

BUT minimal edit constraint is always more important.

================================================================================
VI. Output Schema (DO NOT CHANGE FIELD NAMES)
================================================================================

{
  "candidates": [
    {
      "expression": "single-line factor expression",
      "edit_summary": {
        "edit_direction": "conservative | aggressive | reinforcement",
        "edits": [
          {
            "type": "param_tuning | operator_swap | composition | other",
            "detail": "what changed"
          }
        ]
      },
      "expected_impact": {
        "sharpe_delta": "+0.02~0.08",
        "ic_delta": "+0.001~0.005",
        "turnover_delta": "-3%~-10%",
        "confidence": "low | medium | high"
      },
      "core_logic_preserved": true,
      "deviation_explanation": null
    }
  ]
}

================================================================================
VII. Candidate Diversity Requirement
================================================================================

Generate 2 to 5 candidates with diversity:

- 1 parameter tuning version
- 1 operator swap version
- 1 robustness enhancement version
- 1 turnover reduction version (optional)
- 1 group optimization version (if applicable)

All must remain close neighbors of seed factor.

================================================================================
VIII. Final Reminder (Highest Priority)
================================================================================

You are NOT inventing a new alpha.

You are doing constrained local optimization.

Allowed actions:

- change one operator
OR
- tune one/two parameters

Never add fields.
Never rewrite logic.
Never drift away from seed meaning.

Also obey blacklist_operators / blacklist_fields from the user message when present.

================================================================================
"""


def _minimal_edit_system_prompt() -> str:
    return _MINIMAL_EDIT_RULES.strip()


def _build_user_prompt(
    seed: SeedFactor,
    target_gap: dict,
    knowledge_base: dict | None,
) -> str:
    kb = knowledge_base or {}
    verified = kb.get("verified_rules") or []
    failed = kb.get("failed_paths") or []
    id_tokens = sorted(set(extract_identifier_tokens(seed.expression or "")))
    parts = [
        "=== Seed Factor (anchor) ===",
        f"id: {seed.id}",
        f"name: {seed.name}",
        f"expression: {seed.expression}",
        f"econ_rationale: {seed.econ_rationale}",
        f"market: {seed.market}, universe: {seed.universe}, frequency: {seed.frequency}",
        f"factor_type: {seed.factor_type or ''}",
        f"blacklist_operators: {seed.blacklist_operators or []}",
        f"blacklist_fields: {seed.blacklist_fields or []}",
        "",
        "=== Identifier tokens already present in seed expression (do NOT introduce new data fields) ===",
        json.dumps(id_tokens, ensure_ascii=False),
        "",
        "=== Optimization target (numeric gap) ===",
        f"metric: {target_gap.get('metric', '')}",
        f"current: {target_gap.get('current')}",
        f"target: {target_gap.get('target')}",
        f"constraint: {target_gap.get('constraint', '')}",
        "",
        "=== Knowledge base (optional) ===",
        f"verified_rules: {json.dumps(verified, ensure_ascii=False)}",
        f"failed_paths: {json.dumps(failed, ensure_ascii=False)}",
        "",
        "Output JSON only (single object).",
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

    def _loads(s: str) -> dict:
        data = json.loads(s)
        if not isinstance(data, dict):
            raise ValueError("LLM JSON root must be an object")
        return data

    try:
        return _loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        if start < 0:
            raise
        depth = 0
        for i in range(start, len(raw)):
            ch = raw[i]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return _loads(raw[start : i + 1])
        raise


def _parse_candidates_payload(raw: str) -> list[dict]:
    data = _extract_json_object(raw)
    cands = data.get("candidates")
    if cands is None:
        raise ValueError('JSON must contain key "candidates" (array, may be empty)')
    if not isinstance(cands, list):
        raise ValueError("candidates must be an array")
    if len(cands) == 0:
        return []

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
        item = {**item, "expression": expr}
        out.append(item)
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

    dev = item.get("deviation_explanation")
    deviation_explanation = None
    if dev is not None and dev != "":
        deviation_explanation = str(dev)[:2000]

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
        deviation_explanation=deviation_explanation,
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
        prompt_version="m1-3-v2-en-minimal",
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
