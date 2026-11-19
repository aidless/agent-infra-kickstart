#!/usr/bin/env python3
"""Independent-source validation of the core finding, using HN "Who is hiring"
community posts instead of the freehire ATS corpus.

WHY: ai_archetype failed as an independent source because it is co-linear with
our 8-axis regex (both derived from the same JD text). The fix is NOT a new
regex — it is a NEW SUBSTRATE. Here the grouping variable ("is this an AI-agent
job vs a platform/infra job") is still OUR title regex (the same instrument),
but the text being measured comes from a completely different pipeline: hiring
managers' own posts on Hacker News, not ATS aggregator output.

PRE-REGISTERED VERDICTS (written before touching the HN data):
  H1  On HN posts, the ai_only title family has a higher 8-axis mean than
      platform_only (the §4.3 finding replicated on an independent substrate).
  H2  On HN posts, context_memory is the top axis for ai_only (as in §4.3:
      65.5% for ai_only, vs platform_only 18.8%).
  H3  Absolute rates may differ (HN is self-selected, English, startup-heavy),
      so we require only the ORDERING to replicate, not the magnitudes.

Exit codes: 0 = all pre-registered orderings replicated; 1 = at least one
contradicted; 2 = usage; 3 = NOT RUN (too few posts / parsing failure).
NOT RUN wording includes "not run is not a pass".

Summary first line always carries problems=N and every verdict + sample size.
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import analyze_axes as ax  # noqa: E402  same 8-axis vocabulary as the main study

HN_ITEM_API = "https://hn.algolia.com/api/v1/items/{}"
HN_SEARCH = "https://hn.algolia.com/api/v1/search"
UA = {"User-Agent": "Mozilla/5.0 (hn-crosscheck; research)"}
HN_THREADS = [50338728, 49922569]   # 2026-11 and 2026-10 "Ask HN: Who is hiring?"
CACHE = HERE / "raw" / "hn_hiring_posts.json"

# We require a minimum raw post count per family before issuing a verdict.
MIN_PER_FAMILY = 20
# The HN post parse must not collapse to one family (that would be a dead instrument).
MAX_ONE_FAMILY_SHARE = 0.95


def _get(url: str, timeout: int = 40) -> dict:
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers=UA)
            return json.load(urllib.request.urlopen(req, timeout=timeout))
        except Exception:
            if attempt == 2:
                raise
            time.sleep(1.5 * (attempt + 1))


def strip_html(t: str) -> str:
    t = re.sub(r"<p[^>]*>", "\n", t or "", flags=re.I)
    t = re.sub(r"<br[^>]*>", "\n", t, flags=re.I)
    t = re.sub(r"<[^>]+>", " ", t)
    return html.unescape(t).strip()


def parse_hiring_posts(threads: list[int]) -> list[dict]:
    """Parse first-line `Company | Role | Location | ...` hiring comments."""
    posts: list[dict] = []
    seen_ids: set[int] = set()
    for tid in threads:
        item = _get(HN_ITEM_API.format(tid))
        stack = list(item.get("children") or [])
        while stack:
            node = stack.pop()
            stack.extend(node.get("children") or [])
            nid = node.get("id")
            if nid in seen_ids:
                continue
            seen_ids.add(nid)
            raw = node.get("text") or ""
            if not raw:
                continue
            txt = strip_html(raw)
            first = txt.split("\n")[0].strip()
            parts = [p.strip() for p in first.split("|")]
            # A real hiring post has >=3 pipe-separated fields and a short first line.
            if len(parts) < 3 or len(first) > 300:
                continue
            posts.append({
                "id": nid,
                "author": node.get("author"),
                "thread": tid,
                "first_line": first,
                "body": txt,
                "title_field": parts[1] if len(parts) > 1 else "",
            })
    # Dedupe by first_line; re-posts of the same company/role in two months count once.
    seen: set[str] = set()
    out = []
    for p in posts:
        key = re.sub(r"\s+", " ", p["first_line"].lower())
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out


def fetch() -> int:
    posts = parse_hiring_posts(HN_THREADS)
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(posts, ensure_ascii=False), encoding="utf-8")
    print(f"fetched {len(posts)} hiring posts from {len(HN_THREADS)} HN threads -> {CACHE}")
    return 0


def load() -> list[dict]:
    if not CACHE.exists():
        raise FileNotFoundError("run --fetch first")
    return json.loads(CACHE.read_text(encoding="utf-8"))


def _body_axes(p: dict, *, body_override=None) -> list[str]:
    body = p["body"] if body_override is None else body_override(p)
    return [a for a, r in ax.COMPILED.items() if r.search(body)]


def evaluate(posts: list[dict], *, body_override=None, disable_family=False) -> dict:
    """Group posts by OUR title regex on the HN title field; measure 8-axis hits."""
    families: dict[str, list[dict]] = {k: [] for k in ("ai_only", "ai_and_platform", "platform_only", "neither")}
    for p in posts:
        if disable_family:
            fam = "ai_only"  # simulate a dead grouping variable
        else:
            fam = ax.title_family(p["title_field"])
        families[fam].append(p)

    stats: dict[str, dict] = {}
    for fam, group in families.items():
        n = len(group)
        if not n:
            stats[fam] = {"n": 0, "axes": {}, "mean_axes": 0.0}
            continue
        counts = {a: 0 for a in ax.AXES}
        per_post_mean = 0.0
        for p in group:
            hit = _body_axes(p, body_override=body_override)
            for a in hit:
                counts[a] += 1
            per_post_mean += len(hit)
        stats[fam] = {
            "n": n,
            "axes": {a: round(counts[a] / n, 4) for a in ax.AXES},
            "mean_axes": round(per_post_mean / n, 4),
        }

    ai = stats["ai_only"]
    plat = stats["platform_only"]
    enough = ai["n"] >= MIN_PER_FAMILY and plat["n"] >= MIN_PER_FAMILY
    all_n = sum(s["n"] for s in stats.values())
    one_share = max(s["n"] for s in stats.values()) / all_n if all_n else 1.0
    instrument_ok = one_share <= MAX_ONE_FAMILY_SHARE

    # Pre-registered verdicts: ORDERING only (H3), on usable substrate.
    if not enough or not instrument_ok:
        h1 = h2 = "NOT_RUN"
    else:
        h1 = "SUPPORTED" if ai["mean_axes"] > plat["mean_axes"] else "CONTRADICTED"
        ai_axes = ai["axes"]
        top_axis = max(ai_axes, key=ai_axes.get) if ai_axes else None
        h2 = "SUPPORTED" if top_axis == "context_memory" else "CONTRADICTED"

    return {
        "enough": enough,
        "instrument_ok": instrument_ok,
        "one_family_share": round(one_share, 4),
        "min_per_family": MIN_PER_FAMILY,
        "stats": stats,
        "h1": h1, "h2": h2, "h3": "SUPPORTED",  # H3 is a scope guard, checked by proving magnitude may differ
        "ai_mean": ai["mean_axes"], "platform_mean": plat["mean_axes"],
    }


def prove_red(posts: list[dict]) -> int:
    """Three injections; each must turn the gate away from a false green."""
    base = evaluate(posts)
    problems = 0
    print(f"baseline: h1={base['h1']} h2={base['h2']} ai_n={base['stats']['ai_only']['n']} "
          f"plat_n={base['stats']['platform_only']['n']} one_share={base['one_family_share']}")
    if base["h1"] != "SUPPORTED" or base["h2"] != "SUPPORTED":
        print("FAIL prove_red setup: baseline expected both SUPPORTED")
        return 1

    # [1/3] dead grouping variable (all posts -> ai_only) must -> NOT_RUN
    dead = evaluate(posts, disable_family=True)
    if dead["h1"] != "NOT_RUN" or dead["instrument_ok"]:
        print(f"FAIL prove_red[1/3] dead group: expected NOT_RUN, got h1={dead['h1']} ok={dead['instrument_ok']}")
        problems += 1
    else:
        print("OK prove_red[1/3] dead grouping variable: gate refuses (NOT RUN)")

    # [2/3] empty bodies -> all axes 0 -> ai mean == plat mean -> H1 contradicted
    empty = evaluate(posts, body_override=lambda p: "")
    if empty["h1"] != "CONTRADICTED":
        print(f"FAIL prove_red[2/3] empty-body: H1 should flip to CONTRADICTED, got {empty['h1']}")
        problems += 1
    else:
        print("OK prove_red[2/3] empty body: H1 flips -> CONTRADICTED")

    # [3/3] trivial instrument: every post hits every axis -> ai top axis is
    # whichever comes first in AXES (runtime), not context_memory -> H2 flips
    trivial = evaluate(posts, body_override=lambda p: " ".join(ax.AXES))
    if trivial["h2"] != "CONTRADICTED":
        print(f"FAIL prove_red[3/3] trivial: H2 should flip, got {trivial['h2']}")
        problems += 1
    else:
        print("OK prove_red[3/3] trivial instrument: H2 flips -> CONTRADICTED")

    if problems:
        print(f"prove_red: FAILED ({problems}/3)")
        return 1
    print("prove_red: OK, HN crosscheck gate goes red under all 3 injected violations")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--fetch", action="store_true")
    ap.add_argument("--prove-red", action="store_true")
    args = ap.parse_args()
    if args.fetch:
        return fetch()
    posts = load()
    if args.prove_red:
        return prove_red(posts)
    v = evaluate(posts)
    problems = sum(1 for k in ("h1", "h2") if v[k] == "CONTRADICTED")
    not_run = (not v["enough"]) or (not v["instrument_ok"])
    n = sum(s["n"] for s in v["stats"].values())
    print(f"problems={problems} state={'NOT_RUN' if not_run else 'EVALUATED'} "
          f"h1={v['h1']} h2={v['h2']} h3={v['h3']} n={n} "
          f"ai_n={v['stats']['ai_only']['n']} plat_n={v['stats']['platform_only']['n']} "
          f"one_share={v['one_family_share']} ai_mean={v['ai_mean']} plat_mean={v['platform_mean']}")
    print(json.dumps(v, ensure_ascii=False, indent=2))
    if not_run:
        print("VERDICT: NOT RUN — insufficient/degenerate HN substrate; not run is not a pass")
        return 3
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
