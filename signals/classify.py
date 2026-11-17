#!/usr/bin/env python3
"""Title classifier for the Agent-Infra sample.

The corpus is crawled from ~50 ATS platforms, so the same English word names
unrelated jobs: an "agent" is usually insurance or call-centre work, a "harness"
is usually wiring in an engine bay, and "AI Platform Engineer" at a bank is often
data plumbing. Tiers here are explicit so the sample size is a *stated* number
rather than a vibe:

  tier_A  — infra of the agent itself: runtime, harness, context/memory, tools/MCP,
            sandbox/governance, control plane, eval/gate, observability
  tier_B  — adjacent platform work that plausibly touches agent infra
            (ML platform, inference serving, AI gateway, AI SRE)
  tier_D  — dropped, with the reason recorded, so the drop is auditable and the
            keep set can be re-derived

A title alone cannot settle a tier; `tier` is a *candidate* label and the JD body
tags decide the final signal count. Anything tagged from title only is marked
`evidence: title`.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

# Words whose presence in a title suggests the posting is about building the
# machinery around a model rather than consuming a model.
A_TERMS = {
    "runtime": ["runtime", "durable execution", "stateful", "orchestration engine"],
    "harness": ["harness", "agent framework", "agent loop", "agent orchestration",
                "agent platform", "agentic platform", "agents platform"],
    "context_memory": ["context engineering", "memory", "retrieval", "rag",
                       "vector", "knowledge graph", "embedding"],
    "tool_mcp": ["mcp", "tool calling", "function calling", "tool use", "tools platform",
                 "plugin platform", "integration platform"],
    "sandbox_security": ["sandbox", "guardrail", "agent security", "ai security",
                         "ai governance", "agent identity", "llm security",
                         "trust", "safety engineer"],
    "control_plane": ["control plane", "ai gateway", "llm gateway", "model gateway",
                      "ai platform", "model platform", "inference platform",
                      "serving platform", "ai infrastructure", "agent infrastructure"],
    "eval_gate": ["evaluation", "eval", "benchmark", "quality engineer", "test harness",
                  "red team", "regression"],
    "observability": ["observability", "telemetry", "tracing", "sre", "reliability",
                      "monitoring"],
}
B_TERMS = ["ml platform", "machine learning infrastructure", "ml infrastructure",
           "inference engineer", "serving engineer", "gpu platform", "ai engineer",
           "ai backend", "applied ai", "llm engineer", "genai engineer", "ai devops"]

# Reasons recorded per drop, so "we dropped 3000 postings" is not a black box.
DROP_RULES = [
    ("non_ai_profession", ["customer service", "call centre", "call center", "immobilier",
                           "agent technique", "agent de ", "agent d'", "real estate",
                           "insurance", "travel agent", "sales agent", "agent commercial",
                           "lettings", "estate agent", "booking agent", "talent agent",
                           "funeraire", "funéraire", "entretien", "cnc",
                           "maschinenbediener", "electrician", "leasing agent",
                           "collection agent", "secret agent", "reinigungs", "pflege",
                           "ausbildung", "praktikum", "werkstudent", "ticket agent",
                           "support agent", "helpdesk", "help desk", "service desk",
                           "recruiter", "talent acquisition", "nurse", "teacher",
                           "warehouse", "cleaner", "security guard", "asesor",
                           "kundenberater", "mitarbeiter"]),
    ("wiring_harness", ["wire harness", "harness design", "harness assembly",
                        "electrical harness", "wiring"]),
    ("pure_data_engineering", ["data engineer", "analytics engineer", "data analyst",
                               "bi engineer", "etl developer"]),
    ("non_engineering_role", ["account executive", "account manager", "sales representative",
                              "product marketing", "technical writer", "customer success"]),
]


def classify(title: str) -> tuple[str, list[str], str]:
    """Return (tier, matched_axes, drop_reason)."""
    t = " " + (title or "").lower() + " "
    for reason, words in DROP_RULES:
        if any(w in t for w in words):
            return "D", [], reason
    axes: list[str] = []
    for axis, words in A_TERMS.items():
        if any(w in t for w in words):
            axes.append(axis)
    # "agent" appearing bare is weak on its own (see module docstring) but strong
    # when the title also says engineer/platform/infra.
    has_agent = re.search(r"\bagent(s|ic)?\b", t) is not None
    has_infra = any(w in t for w in ("infra", "platform", "runtime", "harness",
                                     "engineer", "systems", "architecture"))
    if has_agent and has_infra and not axes:
        axes.append("harness")
    if has_agent and has_infra and "runtime" not in axes and re.search(r"\bagent(s)?\s+(runtime|systems)\b", t):
        axes.append("runtime")
    if axes:
        return "A", axes, ""
    if any(w in t for w in B_TERMS):
        return "B", [], ""
    return "D", [], "no_ai_infra_terms"


def main() -> int:
    here = Path(__file__).resolve().parent
    disc = json.loads((here / "raw" / "discovery.json").read_text(encoding="utf-8"))
    tiers = {"A": 0, "B": 0, "D": 0}
    drops: dict[str, int] = {}
    kept: list[dict] = []
    for p in disc["postings"]:
        tier, axes, reason = classify(p.get("title", ""))
        tiers[tier] += 1
        if tier == "D":
            drops[reason] = drops.get(reason, 0) + 1
            continue
        p = dict(p)
        p["tier"] = tier
        p["title_axes"] = axes
        p["evidence"] = "title"
        kept.append(p)
    kept.sort(key=lambda p: (p.get("posted_at") or ""), reverse=True)
    out = here / "raw" / "candidates.json"
    out.write_text(json.dumps({
        "generated_at": disc["generated_at"],
        "discovery_total": disc["count"],
        "tiers": tiers,
        "drop_reasons": drops,
        "count": len(kept),
        "postings": kept,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print("tiers:", tiers)
    print("drop reasons:", drops)
    print(f"candidates: {len(kept)} -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
