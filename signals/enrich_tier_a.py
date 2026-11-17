#!/usr/bin/env python3
"""Stage 3: enrich a ranked, company-capped subset of tier-A/B candidates.

Ranking matters more than volume here. The discovery corpus has 2,483 tier-A
titles, but a large share are one company's 20 near-identical platform reqs —
enriching them all would make the tag frequency mostly a measurement of one
employer's org chart. So candidates are ranked by title specificity, then capped
per company, then enriched with the full JD body.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

UA = "Mozilla/5.0 (X11; Linux x86_64) agent-infra-signal-baseline/1.0"


def title_score(p: dict) -> int:
    """Higher = more likely to be infra-of-the-agent rather than AI-adjacent."""
    t = (p.get("title") or "").lower()
    score = len(p.get("title_axes") or []) * 3
    if p.get("tier") == "A":
        score += 5
    for w in ("infrastructure", "platform", "runtime", "harness", "systems",
              "architecture", "architect", "core", "kernel", "mcp", "eval"):
        if w in t:
            score += 2
    for w in ("intern", "junior", "graduate", "trainee", "apprentice"):
        if w in t:
            score -= 6
    for w in ("manager", "director", "head of", "vp ", "lead product"):
        if w in t:
            score -= 2
    return score


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
    cand = json.loads((here / "raw" / "candidates.json").read_text(encoding="utf-8"))
    ps = cand["postings"]
    ps.sort(key=lambda p: (title_score(p), p.get("posted_at") or ""), reverse=True)

    per_company_cap = int(os.environ.get("PER_COMPANY_CAP", "6"))
    budget = int(os.environ.get("ENRICH_BUDGET", "420"))
    out_name = os.environ.get("ENRICH_OUT", "enriched_a.json")
    # Reuse bodies already fetched by an earlier run: re-fetching them would cost
    # minutes and could return a *different* body than the one already quoted.
    have: dict[str, dict] = {}
    for f in (here / "raw").glob("enriched*.json"):
        for q in json.loads(f.read_text(encoding="utf-8"))["postings"]:
            if q.get("description"):
                have[q["public_slug"]] = q
    chosen: list[dict] = []
    seen_company: Counter = Counter()
    for p in ps:
        co = (p.get("company") or "?").strip().lower()
        if seen_company[co] >= per_company_cap:
            continue
        seen_company[co] += 1
        chosen.append(p)
        if len(chosen) >= budget:
            break
    print(f"chosen {len(chosen)} (budget={budget}, per_company_cap={per_company_cap}) "
          f"from {len(ps)} candidates, {len(set((p.get('company') or '?') for p in ps))} companies")

    enriched: dict[str, dict] = dict(have)
    done = {"n": 0}
    todo = [p for p in chosen if p["public_slug"] not in have]
    print(f"  cached {len(chosen) - len(todo)}, fetching {len(todo)}")

    def work(p: dict) -> None:
        slug = p["public_slug"]
        body = detail(slug)
        if not body:
            return
        merged = dict(p)
        for k in ("description", "skills", "seniority", "category", "work_mode",
                  "regions", "countries", "posted_at", "closed_at", "company",
                  "location", "url", "employment_type", "ai_archetype", "company_size",
                  "company_type", "domains"):
            if k in body and body[k] not in (None, [], ""):
                merged[k] = body[k]
        enriched[slug] = merged
        done["n"] += 1
        if done["n"] % 50 == 0:
            print(f"  {done['n']}/{len(todo)}")

    with ThreadPoolExecutor(max_workers=int(os.environ.get("ENRICH_WORKERS", "8"))) as ex:
        list(ex.map(work, todo))

    out = here / "raw" / out_name
    out.write_text(json.dumps({
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "requested": len(chosen),
        "count": len(enriched),
        "postings": list(enriched.values()),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"enriched total {len(enriched)} ({len(todo)} fetched this run) -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
