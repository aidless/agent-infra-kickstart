#!/usr/bin/env python3
"""Expand the Chinese-language slice of the JD corpus to a size where the
Chinese axis vocabulary can actually be read.

Why a separate fetcher instead of more queries in fetch_freehire.py:

  1. The search endpoint folds a multi-word `q` down to its first token. `q=agent
     harness` returns the same 100830 hits as `q=agent`. So adding English
     phrases never broadens coverage — it only re-asks the same question.
  2. The `countries` facet genuinely narrows (cn=3929 for `q=agent`), and
     Chinese postings are only 56/4017 in the main corpus. Measuring a Chinese
     regex list on 56 rows is measuring noise.

So this pass asks Chinese queries with countries=['cn'], filters to postings
whose body is actually Chinese, and keeps title-relevant ones. Dedupe by
public_slug against every existing enriched file: a posting already measured
is not fetched twice (a second fetch can also return a different revision of
the same JD, which would silently change a quoted number).
"""

from __future__ import annotations

import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

BASE = "https://freehire.me/api/v1/agent/jobs/search"
UA = "Mozilla/5.0 (X11; Linux x86_64) agent-infra-signal-baseline/1.0"
RAW = Path(__file__).resolve().parent / "raw"
OUT = RAW / "enriched_zh.json"

# Chinese queries. Each is a term Chinese JDs actually use, not a translation of
# an English query — "上下文工程" is rare in Chinese postings, "上下文" / "记忆" is
# what they write.
QUERIES = [
    "智能体", "大模型", "大模型应用", "多智能体", "智能体平台", "Agent平台",
    "AI平台", "AI应用", "AI基础设施", "模型服务", "推理", "上下文", "记忆",
    "沙箱", "评测", "MCP", "工具调用", "算法平台", "平台架构", "AI Agent",
    "大模型推理", "模型部署", "向量检索", "检索增强", "Agent开发", "AI安全",
    "提示词", "微调", "训练平台", "算力平台",
]

# A posting is "Chinese" when its body is mostly Chinese characters. Using a
# share instead of a flat count avoids counting one Chinese sentence inside a
# English JD.
def is_zh(body: str, *, min_chars: int = 80, min_share: float = 0.30) -> bool:
    if not body:
        return False
    cjk = sum(1 for c in body if "\u4e00" <= c <= "\u9fff")
    return cjk >= min_chars and cjk / max(len(body), 1) >= min_share


# Title filter: Chinese postings that could plausibly touch the eight axes.
# Kept loose-but-explicit — a title matching nothing here is a different job
# (e.g. 智能体-移动端测试工程师 is QA on an agent product, not agent infra).
TITLE_KEEP = re.compile(
    r"智能体|agent|Agent|大模型|模型|平台|基础设施|架构|harness|Harness|"
    r"沙箱|记忆|上下文|评测|评估|MCP|工具|推理|检索|安全|框架|引擎|中台|Infra|infra",
)
TITLE_DROP = re.compile(
    r"销售|客户经理|运营|客服|招聘|财务|行政|法务|市场|培训|讲师|助教|"
    r"实习生?[-－ ]|校招|应届|测试工程师|移动端测试|产品经理|设计师|ui|UI|视觉设计",
)


def fetch(params: dict, *, retries: int = 3) -> dict:
    url = BASE + "?" + urllib.parse.urlencode(params, doseq=True)
    last: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=90) as r:
                return json.load(r)
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"fetch failed: {url}: {last}")


def have_slugs() -> dict[str, dict]:
    """Every posting already enriched anywhere under raw/, by slug."""
    have: dict[str, dict] = {}
    for f in sorted(RAW.glob("enriched*.json")):
        try:
            rows = json.loads(f.read_text(encoding="utf-8")).get("postings") or []
        except Exception:  # noqa: BLE001
            continue
        for p in rows:
            if p.get("public_slug") and p.get("description"):
                have.setdefault(p["public_slug"], p)
    return have


def title_ok(title: str) -> bool:
    t = title or ""
    if TITLE_DROP.search(t):
        return False
    return bool(TITLE_KEEP.search(t))


def main() -> int:
    budget = int(sys.argv[1]) if len(sys.argv) > 1 else 400
    pages = int(sys.argv[2]) if len(sys.argv) > 2 else 3

    have = have_slugs()
    seen: dict[str, dict] = {}
    per_query: dict[str, int] = {}

    for q in QUERIES:
        for page in range(pages):
            try:
                data = fetch({
                    "q": q, "limit": "100", "offset": str(page * 100),
                    "semantic_ratio": "0", "countries": ["cn"],
                })
            except RuntimeError as e:
                print(f"  ! {q}: {e}", file=sys.stderr)
                break
            rows = data.get("data") or []
            per_query[q] = per_query.get(q, 0) + len(rows)
            for r in rows:
                slug = r.get("public_slug")
                if not slug or slug in have:
                    continue
                body = r.get("description") or ""
                if not is_zh(body):
                    continue
                if not title_ok(r.get("title", "")):
                    continue
                if slug in seen:
                    seen[slug].setdefault("matched_queries", []).append(q)
                    continue
                r = dict(r)
                r["matched_queries"] = [q]
                r["matched_axis"] = "zh"
                seen[slug] = r
            if len(rows) < 100:
                break
        print(f"  {q:12s} raw={per_query.get(q, 0):4d}  zh-kept total={len(seen)}")
        if len(seen) >= budget:
            print(f"  reached budget {budget}, stop")
            break

    # Fold in previously enriched Chinese rows so the output file is the whole
    # Chinese slice, not just this run's增量.
    all_zh = dict(seen)
    for slug, p in have.items():
        if slug in all_zh:
            continue
        if is_zh(p.get("description") or ""):
            all_zh[slug] = p

    OUT.write_text(json.dumps({
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "queries": per_query,
        "count": len(all_zh),
        "this_run_new": len(seen),
        "postings": list(all_zh.values()),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nzh total {len(all_zh)} (new this run {len(seen)}) -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
