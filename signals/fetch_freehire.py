#!/usr/bin/env python3
"""Collect real Agent-Infra job postings from freehire.me's public JSON API.

Two-stage on purpose:
  1. discovery — many queries, title filter only, no description bodies
  2. enrichment — full description for survivors, so every tag is quoted from
     the posting itself instead of inferred from the title.

Params are the agent endpoint's own (q/limit/offset/semantic_ratio/
include_description), not free text guessed at: an ignored query parameter is
the single easiest way to get a plausible-looking corpus that answers nothing.
"""

from __future__ import annotations

import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

BASE = "https://freehire.me/api/v1/agent/jobs/search"
UA = "Mozilla/5.0 (X11; Linux x86_64) agent-infra-signal-baseline/1.0"

# Query groups map to the capability axes this baseline tracks. A posting can
# match several queries; dedupe is by public_slug, so it is one posting, not
# several votes.
QUERIES = {
    "runtime": ["agent runtime", "agent infrastructure engineer", "agent platform engineer",
                "durable execution workflow", "stateful agent",
                "agent execution engine", "long running agent", "agent scheduler",
                "worker sandbox runtime"],
    "harness": ["harness engineer", "agentic harness", "agent framework engineer",
                "agent orchestration engineer", "AI agent engineer",
                "coding agent engineer", "agent developer experience", "agent SDK engineer",
                "multi-agent systems engineer"],
    "context_memory": ["context engineering", "agent memory", "RAG infrastructure",
                       "retrieval engineer", "vector database engineer",
                       "context window management", "agent long term memory",
                       "embedding infrastructure", "semantic search engineer",
                       "knowledge graph engineer"],
    "tool_mcp": ["MCP server engineer", "MCP integration engineer", "tool calling",
                 "function calling engineer", "agent tools",
                 "model context protocol", "tool use reliability", "plugin platform engineer",
                 "actions integration engineer"],
    "sandbox_security": ["agent sandbox", "AI agent security engineer",
                         "agent identity", "AI governance engineer", "LLM security",
                         "prompt injection defense", "AI red team engineer",
                         "non-human identity", "agent authorization",
                         "AI guardrails engineer", "confidential computing AI"],
    "control_plane": ["AI control plane", "model serving platform", "LLM gateway",
                      "AI platform engineer", "inference platform",
                      "token budget platform", "AI cost management", "model routing engineer",
                      "AI quotas rate limiting"],
    "eval_gate": ["AI evaluation engineer", "evaluation infrastructure",
                  "LLM evaluation", "AI quality engineer", "benchmark engineer",
                  "agent evaluation", "regression testing LLM", "human feedback platform",
                  "online evaluation experimentation", "grader rubric engineer"],
    "observability": ["AI observability", "LLM observability engineer",
                      "AI reliability engineer", "AI SRE", "tracing telemetry AI",
                      "agent tracing", "LLM monitoring", "token level logging",
                      "AI incident response"],
    "adjacent_mlplatform": ["ML infrastructure engineer", "LLM infrastructure engineer",
                            "inference engineer", "GPU platform engineer",
                            "AI infrastructure engineer",
                            "training platform engineer", "model lifecycle engineer",
                            "feature store engineer", "distributed training engineer",
                            "MLOps engineer"],
}

# Loose on purpose: real postings say "AI Platform Engineer" or "Agentic AI
# Engineer", rarely "Agent Infra Engineer". A tight filter would quietly drop
# the sample this baseline exists to measure.
KEEP_TOKENS = ["agent", "agentic", "llm", "ai ", "ai/", "genai", "ml ", "ml/",
               "machine learning", "inference", "harness", "mcp", "eval",
               "platform", "infrastructure", "runtime", "orchestration",
               "vector", "retrieval", "rag", "sandbox", "observability",
               "memory", "context", "tool", "security", "guardrail", "identity",
               "telemetry", "tracing", "benchmark", "embedding", "sre", "mlops",
               "gpu", "serving", "red team", "protocol", "scheduler"]

# Non-AI uses of the same words. freehire crawls whole career pages, so "Agent"
# turns up insurance agents and cleaning staff; those are not weak signals, they
# are a different profession.
DROP_TOKENS = ["customer service", "call centre", "call center", "immobilier",
               "agent technique", "agent de ", "agent d'", "real estate",
               "insurance agent", "travel agent", "sales agent", "agent commercial",
               "lettings agent", "estate agent", "booking agent", "talent agent",
               "funeraire", "funéraire", "entretien", "cnc", "maschinenbediener",
               "electrician", "leasing agent", "collection agent", "secret agent",
               "reinigungs", "pflege", "ausbildung", "praktikum", "werkstudent",
               "agent-based", "ticket agent", "support agent", "helpdesk agent"]
# "support agent" is dropped deliberately: it is the most common false friend in
# this corpus, and it is a help-desk job, not an AI infra job.


def fetch(params: dict, *, retries: int = 3) -> dict:
    url = BASE + "?" + urllib.parse.urlencode(params)
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"fetch failed after {retries} tries: {url}: {last}")


def search(q: str, *, limit: int = 100, pages: int = 3) -> list[dict]:
    """Paged keyword search, descriptions off (discovery pass stays cheap)."""
    out: list[dict] = []
    for page in range(pages):
        data = fetch({
            "q": q, "limit": str(limit), "offset": str(page * limit),
            "semantic_ratio": "0", "include_description": "false",
        })
        rows = data.get("data") or []
        out.extend(rows)
        if len(rows) < limit:
            break
    return out


def detail(slug: str) -> dict:
    """Full posting body. The detail endpoint answers a single slug."""
    req = urllib.request.Request(
        f"https://freehire.me/api/v1/jobs/{slug}",
        headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def relevant(title: str) -> bool:
    t = " " + (title or "").lower() + " "
    if any(d in t for d in DROP_TOKENS):
        return False
    return any(k in t for k in KEEP_TOKENS)


def main() -> int:
    raw_dir = Path(__file__).resolve().parent / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    seen: dict[str, dict] = {}
    per_query: dict[str, int] = {}

    for axis, queries in QUERIES.items():
        for q in queries:
            try:
                rows = search(q)
            except RuntimeError as e:
                print(f"  ! {q}: {e}", file=sys.stderr)
                continue
            per_query[q] = len(rows)
            kept = 0
            for r in rows:
                slug = r.get("public_slug")
                if not slug or not relevant(r.get("title", "")):
                    continue
                if slug in seen:
                    seen[slug].setdefault("matched_queries", []).append(q)
                    continue
                r = dict(r)
                r.pop("description", None)
                r["matched_queries"] = [q]
                r["matched_axis"] = axis
                seen[slug] = r
                kept += 1
            print(f"  {axis:20s} {q:34s} {len(rows):3d} raw -> {kept:3d} new (total {len(seen)})")

    out = raw_dir / "discovery.json"
    out.write_text(json.dumps({
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "queries": per_query,
        "count": len(seen),
        "postings": list(seen.values()),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nkept {len(seen)} unique postings -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
