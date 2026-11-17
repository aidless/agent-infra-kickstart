#!/usr/bin/env python3
"""Stage 2: filter the discovery corpus down to AI-agent-infra postings, then
fetch full descriptions for the survivors.

The filter is title-based and deliberately two-sided: a keep list of AI-ish
tokens, a drop list of professions that share the words (insurance agent,
call-centre agent, electrical harness, CNC machine operator). A one-sided filter
on "agent" would make this corpus mostly insurance and cleaning staff — which is
exactly what the first discovery run returned before this list existed.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

UA = "Mozilla/5.0 (X11; Linux x86_64) agent-infra-signal-baseline/1.0"

# A posting must name an AI/agent/LLM thing in its title. Not "platform" or
# "infrastructure" alone: those return every cloud team on the planet.
STRONG = ["agent", "agentic", "llm", "mcp", "harness", "genai", "gen ai",
          "rag", "retrieval", "inference", "eval", "ai ", "ai/", "machine learning",
          "ml ", "ml/", "foundation model", "model serving", "vector"]
DROP = [
    "customer service", "call centre", "call center", "immobilier", "agent technique",
    "agent de ", "agent d'", "real estate", "insurance", "travel agent", "sales agent",
    "agent commercial", "lettings", "estate agent", "booking agent", "talent agent",
    "funeraire", "funéraire", "entretien", "cnc", "maschinenbediener", "electrician",
    "leasing agent", "collection agent", "secret agent", "reinigungs", "pflege",
    "ausbildung", "praktikum", "werkstudent", "ticket agent", "support agent",
    "helpdesk", "help desk", "service desk", "wire harness", "harness design",
    "harness assembly", "electrical harness", "account manager", "recruiter",
    "talent acquisition", "nurse", "teacher", "chef", "driver", "warehouse",
    "cleaner", "security guard", "agent immobilier", "agente", "asesor",
]
# Titles in languages other than English that use the word for a different job.
DROP_LANGS = ["agente ", "agent ", "agente de", "kundenberater", "mitarbeiter"]


def keep(p: dict) -> bool:
    t = " " + (p.get("title") or "").lower() + " "
    if any(d in t for d in DROP):
        return False
    if "electrical" in t or "wiring" in t:
        return False
    return any(k in t for k in STRONG)


def detail(slug: str) -> dict | None:
    url = f"https://freehire.me/api/v1/jobs/{slug}"
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=60) as r:
                body = json.load(r)
            return body.get("data") or body
        except Exception:  # noqa: BLE001
            time.sleep(1.0 * (attempt + 1))
    return None


def main() -> int:
    here = Path(__file__).resolve().parent
    disc = json.loads((here / "raw" / "discovery.json").read_text(encoding="utf-8"))
    survivors = [p for p in disc["postings"] if keep(p)]
    print(f"discovery {disc['count']} -> title-filtered {len(survivors)}")

    # Cap by recency when the corpus is larger than the enrichment budget: an
    # old posting is a weaker signal about what teams are hiring for now.
    cap = int(os.environ.get("ENRICH_CAP", "700"))
    survivors.sort(key=lambda p: (p.get("posted_at") or ""), reverse=True)
    survivors = survivors[:cap]
    print(f"enriching {len(survivors)} postings (cap={cap})")

    enriched: dict[str, dict] = {}
    lock_n = {"done": 0}

    def work(p: dict) -> None:
        slug = p["public_slug"]
        body = detail(slug)
        if not body:
            return
        merged = dict(p)
        for k in ("description", "skills", "seniority", "category", "work_mode",
                  "regions", "countries", "posted_at", "closed_at", "company",
                  "location", "url", "employment_type", "ai_archetype"):
            if k in body and body[k] not in (None, [], ""):
                merged[k] = body[k]
        enriched[slug] = merged
        lock_n["done"] += 1
        if lock_n["done"] % 50 == 0:
            print(f"  enriched {lock_n['done']}/{len(survivors)}")

    with ThreadPoolExecutor(max_workers=8) as ex:
        list(ex.map(work, survivors))

    print(f"enriched {len(enriched)} / {len(survivors)}")
    out = here / "raw" / "enriched.json"
    out.write_text(json.dumps({
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "count": len(enriched),
        "postings": list(enriched.values()),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"-> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
