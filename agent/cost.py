from __future__ import annotations

"""Token estimation and cost arithmetic for trace rows.

Two rules this module exists to satisfy:
  1. A number on a trace row must be recomputable from the row itself. So every
     row carries `tokens_in_est`, `tokens_out_est`, `price_id`, and `cost_usd`,
     and `compute_cost` is a pure function of the first three.
  2. A number on a trace row must not pretend to be something it is not. These are
     *estimates* from a documented heuristic (`estimate_v1`), not tokenizer output,
     and the price table below is a local fixture for exercising the cost path,
     not a vendor quote.

`estimate_v1` — deterministic, dependency-free:
    tokens = (number of CJK codepoints) + ceil((other codepoints) / 4)

CJK codepoints are counted 1:1 because a common byte-pair vocabulary gives them
roughly one token each; the remaining characters are Latin/digits/punctuation and
average about four per token. This is deliberately crude. It is useful for
comparing one run against another and for catching a step whose output suddenly
grew 10x. It is not a billing figure.
"""

import math
from typing import Any, Dict

ESTIMATOR_ID = "estimate_v1"
_ASCII_PER_TOKEN = 4

# Local pricing fixture. Named so a trace row records which table it used.
# Changing a rate here changes every recomputation, so the price_id travels with
# the row and old rows stay interpretable after the table is edited.
PRICING: Dict[str, Dict[str, float]] = {
    # price_id: {in_per_mtok, out_per_mtok} in USD per million tokens
    "fixture-standard": {"in_per_mtok": 3.00, "out_per_mtok": 15.00},
    "fixture-cheap": {"in_per_mtok": 0.10, "out_per_mtok": 0.40},
}
DEFAULT_PRICE_ID = "fixture-standard"


def _is_cjk(ch: str) -> bool:
    o = ord(ch)
    return (
        0x4E00 <= o <= 0x9FFF      # CJK unified ideographs
        or 0x3400 <= o <= 0x4DBF   # extension A
        or 0xF900 <= o <= 0xFAFF   # compatibility ideographs
        or 0x3000 <= o <= 0x303F   # CJK punctuation
        or 0xFF00 <= o <= 0xFFEF   # fullwidth forms
    )


def estimate_tokens(text: str) -> int:
    """Deterministic token estimate for `text` (see module docstring)."""
    if not text:
        return 0
    cjk = sum(1 for ch in text if _is_cjk(ch))
    other = len(text) - cjk
    return cjk + math.ceil(other / _ASCII_PER_TOKEN)


def estimate_tokens_for_payload(payload: Any) -> int:
    """Estimate tokens for a tool argument or tool output payload."""
    if payload is None:
        return 0
    import json

    if isinstance(payload, str):
        text = payload
    else:
        text = json.dumps(payload, ensure_ascii=False, default=str)
    return estimate_tokens(text)


def compute_cost(tokens_in: int, tokens_out: int, price_id: str = DEFAULT_PRICE_ID) -> float:
    """USD cost for a step, from the recorded price table. Pure, recomputable."""
    table = PRICING.get(price_id)
    if table is None:
        raise KeyError(f"unknown price_id: {price_id}")
    return (
        tokens_in * table["in_per_mtok"] + tokens_out * table["out_per_mtok"]
    ) / 1_000_000.0


def rates_for(price_id: str = DEFAULT_PRICE_ID) -> Dict[str, float]:
    """The two rates a row was priced at, copied onto the row itself.

    A row must stay interpretable after the table is edited, so the rates travel
    with the row. Editing PRICING then changes new rows only, which is the point:
    an old number is never silently re-based onto a new price.
    """
    table = PRICING.get(price_id)
    if table is None:
        raise KeyError(f"unknown price_id: {price_id}")
    return {"in_per_mtok": table["in_per_mtok"], "out_per_mtok": table["out_per_mtok"]}


def cost_from_rates(tokens_in: int, tokens_out: int, in_per_mtok: float, out_per_mtok: float) -> float:
    """USD cost from explicit rates. This is what a trace row is checked against."""
    return (tokens_in * in_per_mtok + tokens_out * out_per_mtok) / 1_000_000.0


def cost_fields(args_payload: Any, output_payload: Any, price_id: str = DEFAULT_PRICE_ID) -> Dict[str, Any]:
    """The trace fields that make a step's cost auditable.

    Tokens are estimated, rates are copied onto the row, and cost_usd is derived
    from the two — so every number on the row can be recomputed from the row
    alone, with no reference to a table that may have changed since.
    """
    tokens_in = estimate_tokens_for_payload(args_payload)
    tokens_out = estimate_tokens_for_payload(output_payload)
    rates = rates_for(price_id)
    return {
        "estimator": ESTIMATOR_ID,
        "price_id": price_id,
        "price_in_per_mtok": rates["in_per_mtok"],
        "price_out_per_mtok": rates["out_per_mtok"],
        "tokens_in_est": tokens_in,
        "tokens_out_est": tokens_out,
        "cost_usd": cost_from_rates(tokens_in, tokens_out, rates["in_per_mtok"], rates["out_per_mtok"]),
    }
