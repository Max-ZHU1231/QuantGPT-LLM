#!/usr/bin/env python3
"""锚因子演示：读取锚定表达式，调用 DeepSeek（DEEPSEEK_*）生成一条改进因子表达式。

加载顺序（后者覆盖前者）：先 `.env.example` 缺省项，再 `.env` 全覆盖。
建议：真实密钥只放在 `.env`（且勿提交）；勿把有效 Key 长期留在已入库的 `.env.example`。

用法:
  python scripts/anchor_factor_demo.py
  echo rank(close/ts_mean(close,20)) | python scripts/anchor_factor_demo.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv_file(path: Path, *, override: bool) -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip()
        if override:
            os.environ[key] = val
        else:
            os.environ.setdefault(key, val)


# Files override inherited shell env (e.g. stray DEEPSEEK_API_KEY=dummy in CI).
# Precedence: .env.example then .env (later wins per key).
_load_dotenv_file(_ROOT / ".env.example", override=True)
_load_dotenv_file(_ROOT / ".env", override=True)

if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def main() -> None:
    print("QuantGPT — 锚因子 → DeepSeek 生成改进表达式\n", flush=True)

    anchor = ""
    if not sys.stdin.isatty():
        anchor = sys.stdin.read().strip()
    if not anchor:
        anchor = input("请输入锚因子表达式（必填）: ").strip()

    if not anchor:
        print("错误：锚因子不能为空")
        sys.exit(1)

    extra = ""
    if sys.stdin.isatty():
        extra = input("可选：改进方向一句话（回车跳过）: ").strip()

    from quantgpt.llm_service import call_deepseek

    if extra:
        prompt = (
            f"锚定因子表达式（请在保留其核心逻辑的前提下改进）：{anchor}\n"
            f"改进方向：{extra}"
        )
    else:
        prompt = (
            "锚定因子表达式如下，请在保留其核心经济含义的前提下，生成更稳健、"
            "可多维度组合的改进版本（只输出一行可执行表达式）：\n"
            f"{anchor}"
        )

    try:
        out = call_deepseek(prompt)
        print("\n--- DeepSeek 输出 ---\n")
        print(out)
    except Exception as e:
        print(f"调用失败: {e}")
        sys.exit(2)


if __name__ == "__main__":
    main()
