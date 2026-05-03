"""Backward-compat shim — implementation lives in ``quantgpt.factor_pipeline.minimal_edit_generator``.

Prefer importing from ``quantgpt.factor_pipeline.minimal_edit_generator`` (or ``quantgpt.factor_pipeline`` lazy attrs).

单元测试若 monkeypatch LLM，应对 ``quantgpt.factor_pipeline.minimal_edit_generator`` 打补丁，而非本模块。
"""

from quantgpt.factor_pipeline.minimal_edit_generator import (
    generate_minimal_edits_for_seed,
    get_batch_for_user,
)

__all__ = ["generate_minimal_edits_for_seed", "get_batch_for_user"]
