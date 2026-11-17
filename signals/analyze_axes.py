#!/usr/bin/env python3
"""Stage 4: measure the eight capability axes on real JD bodies, with quotes.

Why this exists: title keywords alone are a weak instrument. A posting called
"Senior Software Engineer, Platform" can carry an entire agent-runtime
requirement list in its body, and a posting called "AI Engineer" can be a
prompt-writing role. So every axis is measured on two levels and reported as a
pair:

  title_rate  — the axis is in the job title (the role is *named* this)
  body_rate   — the axis is in the requirement text (the role *does* this)
  hidden      — body_rate minus title_rate: capability absorbed into other
                titles, i.e. the axis is a horizontal skill rather than a job

`required` vs `preferred` comes from the API's own requirement extraction
(enrichment.requirements[].priority), not from our guess about tone.

Discipline: this script carries a --selftest that plants one positive and one
negative sentence per axis and asserts the matcher separates them. A counter
that cannot come back zero is a decoration, so selftest also asserts an
unrelated sentence produces zero hits on every axis.
"""

from __future__ import annotations

import argparse
import html
import json
import math
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
RAW = HERE / "raw"

# Axis patterns are deliberately narrow-ish: each must name the *mechanism*, not
# just the domain. "AI" alone never matches anything here.
AXES: dict[str, dict] = {
    "runtime": {
        "label": "Agent Runtime / 执行引擎",
        "patterns": [
            r"agent(ic)? runtime", r"runtime (for|of) (ai )?agents",
            r"durable execution", r"durable workflow", r"execution engine",
            r"stateful (agent|workflow|session)", r"long[- ]running (agent|job|task)",
            r"agent (scheduler|scheduling|execution)", r"workflow orchestration (engine|layer)",
            r"checkpoint(ing)? (of )?(agent|workflow|run)", r"resumable (run|agent|execution)",

            r"执行引擎",
            r"长任务",
            r"断点(恢复|续跑)",
            r"状态快照",
            r"会话生命周期",
            r"任务状态(管理|机)",
            r"弹性(运行|调度)",
            r"checkpoint",
        ],
    },
    "harness": {
        "label": "Harness / Agent 框架与循环",
        "patterns": [
            r"agent(ic)? (loop|harness|framework|scaffold)",
            r"harness (for|around) (agents|models)",
            r"tool[- ]calling loop", r"reason[- ]act", r"plan[- ]and[- ]execute",
            r"multi[- ]agent (system|orchestration|framework)",
            r"agent orchestration", r"agent sdk", r"developer experience for agent",

            r"(agent|ai|model) harness",
            r"harness (engineering|architecture|kernel|runtime)",
            r"agent loop",
            r"推理[-－—]行动循环",
            r"智能体(框架|编排|循环)",
            r"多\s*agent\s*编排",
            r"skill\s*体系",
            r"skill (加载|注册|体系|机制)",
            r"(agent|tool|ai) skills",
        ],
    },
    "context_memory": {
        "label": "Context & Memory / 上下文与记忆",
        "patterns": [
            r"context (window|engineering|management|compression|budget)",
            r"agent memory", r"long[- ]term memory", r"memory (system|store|layer)",
            r"retrieval[- ]augmented", r"\brag\b", r"vector (database|store|index)",
            r"embedding(s)? (pipeline|infrastructure|service|index)",
            r"semantic (search|cache)", r"knowledge graph",

            r"上下文(管理|压缩|工程|编排)",
            r"长期记忆",
            r"记忆(管理|机制|体系)",
            r"检索增强",
            r"向量(库|检索|索引)",
            r"知识(图谱|检索)",
            r"token\s*效率",
        ],
    },
    "tool_mcp": {
        "label": "Tool / MCP / 工具协议",
        "patterns": [
            r"model context protocol", r"\bmcp\b",
            r"tool (calling|use|invocation|registry)", r"function calling",
            r"tool (schema|definition|permission)", r"plugin (platform|architecture) for (agent|ai)",

            r"工具(调用|注册|编排|接入)",
            r"函数调用",
            r"mcp",
            r"插件(机制|体系|化接入)",
            r"技能加载",
        ],
    },
    "sandbox_security": {
        "label": "Sandbox / Credential / Identity / 安全治理",
        "patterns": [
            r"sandbox(ing|ed)? (execution|environment|runtime)",
            r"isolated (environment|execution)", r"code execution (environment|sandbox)",
            r"prompt injection", r"jailbreak", r"guardrail",
            r"non[- ]human identity", r"agent identity", r"scoped credential",
            r"credential (management|broker|vault)", r"secret (management|rotation)",
            r"least privilege", r"rbac", r"policy engine", r"red team",
            r"confidential computing", r"data residency",

            r"沙箱",
            r"隔离",
            r"权限(边界|模型|审批|隔离)",
            r"凭证",
            r"越权",
            r"注入(防护|攻击)",
            r"审计",
            r"合规",
            r"可信执行",
        ],
    },
    "control_plane": {
        # "control plane" alone is Kubernetes vocabulary (etcd/CNI/kubelet), not
        # the AI control plane. Bare hits are kept as the topic `k8s_control_plane`
        # so the collision stays visible instead of silently inflating this axis.
        "label": "Control Plane / AI 网关与成本控制",
        "patterns": [
            r"(ai|model|agent|llm|inference|token)[- ](control plane)",
            r"control plane (for|of) (ai|agents?|llm|models?|inference)",
            r"(llm|model|ai|token) gateway", r"model routing", r"model router",
            r"rate limit(ing)? (for|of|on) (ai|llm|model|inference)",
            r"token (budget|cost|accounting|spend)", r"token quota",
            r"cost (attribution|control|optimization) (for|of) (ai|llm|inference)",

            r"网关",
            r"限流",
            r"配额",
            r"token\s*成本",
            r"模型路由",
            r"调度策略",
            r"成本(优化|控制|可视化)",
        ],
    },
    "eval_gate": {
        "label": "Eval / Gate / 质量闸",
        "patterns": [
            r"eval(uation)? (harness|infrastructure|platform|pipeline|suite)",
            r"(offline|online) eval(uation)?", r"llm[- ]as[- ]judge", r"grader",
            r"benchmark (suite|harness|infrastructure)", r"regression (test|suite|gate) for (ai|llm|agent)",
            r"golden (set|dataset)", r"human (feedback|labeling|evaluation)",
            r"acceptance (gate|criteria) for (agent|ai|model)", r"quality gate",
            r"a/?b test(ing)? (for|of) (llm|model|prompt)",

            r"评测(体系|集|数据|平台)",
            r"评估(体系|集|器)",
            r"回归(门禁|测试|迭代)",
            r"打分",
            r"benchmark",
            r"bad\s*case",
            r"轨迹(分析|反馈)",
        ],
    },
    "observability": {
        # AI-specific observability only. Generic SRE vocabulary (on-call, incident
        # response, reliability engineering) is measured separately as a topic:
        # it appears in nearly every infra JD and would otherwise swallow the axis.
        "label": "Observability / 可观测（AI 专项）",
        "patterns": [
            r"observability (for|of) (ai|agents?|llm|models?)",
            r"ai observability", r"llm observability", r"agent observability",
            r"distributed tracing", r"trace(s|ing)? (for|of) (agent|llm|ai)",
            r"(agent|llm) trace", r"trace (data model|context propagation|visualization)",
            r"telemetry (for|of) (ai|agents?|llm)", r"open?telemetry",
            r"span (data model|enricher)", r"token[- ]level logging",
            r"prompt (logging|audit)", r"agent (trajectory|session) (logging|replay|inspection)",
            r"(eval|agent) replay", r"debugging (agent|llm) (runs|trajectories)",

            r"可观测",
            r"链路追踪",
            r"全链路",
            r"诊断能力",
            r"监控告警",
            r"tracing",
            r"trace\b",
        ],
    },
}

# Cross-cutting topics: not axes, but the vocabulary that decides whether the
# axis is a *named* concern yet or only an implicit one.
TOPICS: dict[str, dict] = {
    "agent_word":     {"label": "提到 agent/agentic", "patterns": [r"agentic", r"\bagents?\b"]},
    "llm_word":       {"label": "提到 LLM/大模型", "patterns": [r"\bllm", r"large language model", r"foundation model", r"generative ai", r"genai"]},
    "mcp_word":       {"label": "提到 MCP 协议", "patterns": [r"model context protocol", r"\bmcp\b"]},
    "prompt_inj":     {"label": "提到提示注入", "patterns": [r"prompt injection", r"jailbreak"]},
    "cost_token":     {"label": "提到 token 成本/预算", "patterns": [r"token (cost|budget|spend|accounting)", r"cost per token", r"inference cost"]},
    "latency":        {"label": "提到延迟/吞吐", "patterns": [r"latency", r"throughput", r"p ?99"]},
    "open_source":    {"label": "提到开源/自建框架", "patterns": [r"langchain", r"langgraph", r"autogen", r"llamaindex", r"crewai", r"semantic kernel", r"open source"]},
    "prod_scale":     {"label": "提到生产规模/大规模", "patterns": [r"production (grade|scale)", r"at scale", r"high[- ]volume", r"millions of"]},
    "onprem_cloud":   {"label": "提到云平台", "patterns": [r"aws", r"gcp", r"azure", r"kubernetes"]},
    "generic_ops":    {"label": "通用运维词（SRE/on-call/事故响应）",
                       "patterns": [r"sre\b", r"on[- ]call", r"incident (response|management)",
                                    r"reliability engineering", r"pager duty"]},
    "k8s_control":    {"label": "control plane（K8s 语境）",
                       "patterns": [r"control plane"]},
    "eval_word":      {"label": "提到 eval/evaluation（不限机制）",
                       "patterns": [r"eval(uation)?\b", r"benchmark", r"graders?\b"]},
}


def clean_html(t: str) -> str:
    """HTML → line-preserving plain text (lines are the quote unit)."""
    if not t:
        return ""
    t = re.sub(r"<br[^>]*>", "\n", t, flags=re.I)
    t = re.sub(r"</p>", "\n\n", t, flags=re.I)
    t = re.sub(r"<p[^>]*>", "\n\n", t, flags=re.I)
    t = re.sub(r"<li[^>]*>", "\n• ", t, flags=re.I)
    t = re.sub(r"</li>", "\n", t, flags=re.I)
    t = re.sub(r"<[^>]+>", " ", t)
    t = html.unescape(t).replace("\xa0", " ")
    lines = [re.sub(r"\s+", " ", ln).strip(" •\t") for ln in t.split("\n")]
    return "\n".join(ln for ln in lines if ln)


def sentences(text: str) -> list[str]:
    """Requirement-sized units: lines, then split on sentence punctuation."""
    out = []
    for ln in text.split("\n"):
        for piece in re.split(r"(?<=[.;!?])\s+", ln):
            piece = piece.strip(" •")
            if len(piece) >= 8:
                out.append(piece)
    return out


def compile_axis(patterns: list[str]) -> re.Pattern:
    return re.compile(r"(?:" + "|".join(patterns) + r")", re.I)


COMPILED = {k: compile_axis(v["patterns"]) for k, v in AXES.items()}
COMPILED_TOPICS = {k: compile_axis(v["patterns"]) for k, v in TOPICS.items()}


def load_corpus(globs: list[str] | None = None) -> list[dict]:
    """Read one or more enriched files; dedupe by slug so a re-run does not double
    count a posting that appears in both an old and a new export."""
    rows: list[dict] = []
    seen: set[str] = set()
    names = globs or ["enriched_a.json"]
    files: list[Path] = []
    for name in names:
        files.extend(sorted(RAW.glob(name)))
    for f in files:
        for p in json.loads(f.read_text(encoding="utf-8"))["postings"]:
            slug = p.get("public_slug")
            if not slug or slug in seen:
                continue
            seen.add(slug)
            rows.append(p)
    return rows


def axis_hits(body: str, reqs: list[dict]) -> dict[str, dict]:
    res: dict[str, dict] = {}
    for axis, rx in COMPILED.items():
        body_hit = bool(rx.search(body))
        req_hit: Counter = Counter()
        quote = None
        for r in reqs or []:
            txt = r.get("text") or ""
            if rx.search(txt):
                req_hit[r.get("priority") or "unknown"] += 1
                if quote is None and 20 <= len(txt) <= 320:
                    quote = txt.strip()
        res[axis] = {
            "body": body_hit,
            "req_required": req_hit.get("required", 0),
            "req_preferred": req_hit.get("preferred", 0),
            "quote": quote,
        }
    return res


MIN_SEN_N = 25  # below this a seniority group is小样本噪音, not a rate
MIN_FAM_N = 40   # same guard for the title-family split

# Two independent title tests, crossed. The single-regex cohorts above answer
# "does an agent-named role ask for more axes"; this answers "is it the AI-ness
# or the platform-ness that brings the axes". Crossing them matters because
# platform-only titles (SRE / infra / architect) look like this baseline's
# target audience but ask for the fewest axes of any family.
# Bilingual on purpose. An English-only title test on the Chinese slice put 64% of
# rows into "neither" — the same defect the axis vocabulary had before Chinese
# patterns were added. 智能体/大模型 say "AI" and 平台/架构师 say "platform".
# NOTE: no bare `\bai\b`. It scores 3x better on recall and destroys precision —
# "AI Data Engineer" and "GenAI-Driven Data Platforms" are data roles, and adding
# it moved 966 postings into ai_and_platform while dropping that family's mean
# axes from 2.36 to 1.70. The family split is about the *agent/LLM* vocabulary.
TITLE_AI = re.compile(r"agent|agentic|\bllm|ai engineer|genai|generative ai|"
                      r"applied ai|ml engineer|智能体|大模型", re.I)
TITLE_PLATFORM = re.compile(r"platform|infrastructure|\binfra\b|sre\b|reliability|"
                            r"devops|architect|architecture|runtime|harness|kernel|"
                            r"平台|基础设施|中台|架构师|系统架构|执行引擎", re.I)


def title_family(title: str) -> str:
    t = title or ""
    ai = bool(TITLE_AI.search(t))
    pl = bool(TITLE_PLATFORM.search(t))
    if ai and pl:
        return "ai_and_platform"
    if ai:
        return "ai_only"
    if pl:
        return "platform_only"
    return "neither"



def seniority_of(p: dict) -> str | None:
    """Seniority lives in the `enrichment` sub-object; the TOP-LEVEL field is
    null on every row of this corpus. Reading the wrong one returns an empty
    table that looks like "this corpus has no seniority data" — so the read
    lives in one function that the selftest can point at."""
    return (p.get("enrichment") or {}).get("seniority")


def analyze(rows: list[dict]) -> dict:
    n = len(rows)
    ax_present: Counter = Counter()
    ax_title: Counter = Counter()
    ax_req_req: Counter = Counter()
    ax_req_pref: Counter = Counter()
    quotes: dict[str, list[dict]] = defaultdict(list)
    cat_by_axis: dict[str, Counter] = defaultdict(Counter)
    co = Counter()
    topic: Counter = Counter()
    title_hits: dict[str, int] = defaultdict(int)

    for p in rows:
        title = (p.get("title") or "").lower()
        body = clean_html(p.get("description") or "")
        reqs = ((p.get("enrichment") or {}).get("requirements")) or []
        cat = (p.get("enrichment") or {}).get("category") or "unknown"
        hits = axis_hits(body, reqs)
        present = [a for a, h in hits.items() if h["body"]]
        for a, h in hits.items():
            if re.search(COMPILED[a].pattern, title, re.I):
                ax_title[a] += 1
                title_hits[a] += 1
            if h["body"]:
                ax_present[a] += 1
                cat_by_axis[a][cat] += 1
                if len(quotes[a]) < 400 and h["quote"]:
                    quotes[a].append({
                        "company": p.get("company"), "title": p.get("title"),
                        "url": p.get("url"), "quote": h["quote"],
                    })
            ax_req_req[a] += h["req_required"]
            ax_req_pref[a] += h["req_preferred"]
        for i, a in enumerate(present):
            for b in present[i + 1:]:
                co[tuple(sorted((a, b)))] += 1
        for t, rx in COMPILED_TOPICS.items():
            if rx.search(body) or rx.search(title):
                topic[t] += 1

    # Depth: how many axes one posting wants at once. A "single-axis" JD is a
    # specialist req; 4+ axes is the same person owning runtime, tools, memory
    # and eval — that is the shape this baseline is looking for.
    depth = Counter()
    for p in rows:
        body = clean_html(p.get("description") or "")
        reqs = ((p.get("enrichment") or {}).get("requirements")) or []
        hits = axis_hits(body, reqs)
        k = sum(1 for h in hits.values() if h["body"])
        depth[k] += 1

    # Title cohort split: does an agent/LLM *named* role ask for more axes than a
    # generically-named platform role? If yes, the axes are becoming the job; if
    # no, they are a horizontal skill spread across every infra title.
    cohorts: dict[str, dict] = {}
    for name, rx in (("agent_named", re.compile(r"agent|agentic", re.I)),
                     ("llm_named", re.compile(r"\bllm|ai engineer|genai|generative ai", re.I)),
                     ("platform_named", re.compile(r"platform|infrastructure|sre|reliability|devops", re.I))):
        sub = [p for p in rows if rx.search(p.get("title") or "")]
        if not sub:
            continue
        c: Counter = Counter()
        kc: Counter = Counter()
        for p in sub:
            body = clean_html(p.get("description") or "")
            reqs = ((p.get("enrichment") or {}).get("requirements")) or []
            hits = axis_hits(body, reqs)
            for a, h in hits.items():
                if h["body"]:
                    c[a] += 1
            kc[sum(1 for h in hits.values() if h["body"])] += 1
        cohorts[name] = {
            "n": len(sub),
            "axes": {a: round(c[a] / len(sub), 4) for a in AXES},
            "mean_axes": round(sum(k * v for k, v in kc.items()) / len(sub), 2),
        }

    # Freshness slice: an axis that only lives in 2021-era postings is a faded
    # requirement, not a current one. Fresh <90d vs stale >365d, same matcher.
    import datetime as _dt
    _now = _dt.datetime.now(_dt.timezone.utc)

    def _age_days(p: dict) -> int | None:
        raw = p.get("posted_at")
        if not raw:
            return None
        try:
            d = _dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
        return (_now - d).days

    slices: dict[str, list[dict]] = {"fresh_90d": [], "stale_365d": []}
    for p in rows:
        a = _age_days(p)
        if a is None:
            continue
        if a <= 90:
            slices["fresh_90d"].append(p)
        elif a > 365:
            slices["stale_365d"].append(p)

    fresh_vs_stale: dict[str, dict] = {}
    for a in AXES:
        vals = {}
        for name, sub in slices.items():
            if not sub:
                continue
            c = sum(1 for p in sub
                    if COMPILED[a].search(clean_html(p.get("description") or "")))
            vals[name] = {"n": len(sub), "rate": round(c / len(sub), 4)}
        if vals:
            fresh_vs_stale[a] = vals

    # Year cohorts: the actual "wind direction" instrument. Each year's postings
    # are scored by the same matcher; if an axis climbs across cohorts it is
    # entering the standard req list, if it is flat it was already standard, and
    # if it decays the vocabulary was a passing fashion.
    year_of: dict[int, list[dict]] = defaultdict(list)
    for p in rows:
        a = _age_days(p)
        raw = p.get("posted_at")
        if not raw:
            continue
        try:
            y = _dt.datetime.fromisoformat(raw.replace("Z", "+00:00")).year
        except ValueError:
            continue
        year_of[y].append(p)

    # Month cohorts inside the current window. The year split is nearly useless
    # here (2025 holds 44 of 4,017 postings), so the honest instrument is the
    # recent months where each cohort has >= MIN_MONTH_N postings.
    MIN_MONTH_N = 50
    month_of: dict[str, list[dict]] = defaultdict(list)
    for p in rows:
        raw = p.get("posted_at")
        if not raw:
            continue
        month_of[raw[:7]].append(p)

    month_trend: dict[str, dict] = {}
    for a in list(AXES) + [f"topic:{t}" for t in TOPICS]:
        rx = COMPILED[a] if a in AXES else COMPILED_TOPICS[a.split(":", 1)[1]]
        per_month = {}
        for m, sub in sorted(month_of.items()):
            if len(sub) < MIN_MONTH_N:
                continue
            c = sum(1 for p in sub
                    if rx.search(clean_html(p.get("description") or "")
                                 + " " + (p.get("title") or "")))
            per_month[m] = {"n": len(sub), "rate": round(c / len(sub), 4)}
        if len(per_month) >= 3:
            month_trend[a] = per_month

    year_trend: dict[str, dict] = {}
    for a in list(AXES) + [f"topic:{t}" for t in TOPICS]:
        rx = COMPILED[a] if a in AXES else COMPILED_TOPICS[a.split(":", 1)[1]]
        per_year = {}
        for y, sub in sorted(year_of.items()):
            if len(sub) < 20:
                continue
            c = sum(1 for p in sub
                    if rx.search(clean_html(p.get("description") or "")
                                 + " " + (p.get("title") or "")))
            per_year[str(y)] = {"n": len(sub), "rate": round(c / len(sub), 4)}
        if len(per_year) >= 2:
            year_trend[a] = per_year


    rates = {
        a: {
            "label": AXES[a]["label"],
            "title_rate": round(ax_title[a] / n, 4) if n else 0.0,
            "body_rate": round(ax_present[a] / n, 4) if n else 0.0,
            "hidden_rate": round((ax_present[a] - ax_title[a]) / n, 4) if n else 0.0,
            "required_mentions": ax_req_req[a],
            "preferred_mentions": ax_req_pref[a],
            "required_rate": round(ax_req_req[a] / n, 4) if n else 0.0,
            "preferred_rate": round(ax_req_pref[a] / n, 4) if n else 0.0,
            # hard:soft = how many "required" items per "preferred" item. A JD that
            # calls an axis required is making a hiring commitment, not listing a
            # nice-to-have; the ratio separates those two kinds of signal.
            "hard_soft": round(ax_req_req[a] / ax_req_pref[a], 2) if ax_req_pref[a] else None,
            "top_categories": cat_by_axis[a].most_common(3),
        } for a in AXES
    }

    co_rows = []
    for (a, b), c in co.most_common():
        pa, pb = ax_present[a] / n, ax_present[b] / n
        lift = (c / n) / (pa * pb) if pa and pb else 0.0
        co_rows.append({"a": a, "b": b, "both": c, "p_both": round(c / n, 4),
                        "expected_if_independent": round(pa * pb, 4), "lift": round(lift, 3)})

    # Title-family slice: cross the AI-name test with the platform-name test.
    # A role that is both is the shape the axes actually converge into; a role
    # that is only platform-named is infra work whose JD rarely mentions agents.
    fam_groups: dict[str, list[dict]] = defaultdict(list)
    for p in rows:
        fam_groups[title_family(p.get("title") or "")].append(p)
    fam_report: dict[str, dict] = {}
    for fam, sub in fam_groups.items():
        if len(sub) < MIN_FAM_N:
            continue
        c: Counter = Counter()
        kc: Counter = Counter()
        for p in sub:
            body = clean_html(p.get("description") or "")
            for a in AXES:
                if COMPILED[a].search(body):
                    c[a] += 1
            kc[sum(1 for a in AXES if COMPILED[a].search(body))] += 1
        fam_report[fam] = {
            "n": len(sub),
            "share": round(len(sub) / n, 4) if n else 0.0,
            "axes": {a: round(c[a] / len(sub), 4) for a in AXES},
            "mean_axes": round(sum(k * v for k, v in kc.items()) / len(sub), 2),
        }

    # Seniority slice: does an axis belong to a level? `enrichment.seniority` is
    # populated for ~45% of rows while the top-level field is all None, so this
    # reads the sub-object explicitly and reports the coverage it actually has.
    sen_groups: dict[str, list[dict]] = defaultdict(list)
    for p in rows:
        sv = seniority_of(p)
        if sv:
            sen_groups[sv].append(p)
    sen_report: dict[str, dict] = {}
    for sv, sub in sen_groups.items():
        if len(sub) < MIN_SEN_N:
            continue
        c: Counter = Counter()
        for p in sub:
            body = clean_html(p.get("description") or "")
            for a in AXES:
                if COMPILED[a].search(body):
                    c[a] += 1
        sen_report[sv] = {"n": len(sub),
                          "axes": {a: round(c[a] / len(sub), 4) for a in AXES}}

    return {
        "n_postings": n,
        "axes": rates,
        "title_families": {"min_group": MIN_FAM_N, "groups": fam_report},
        "seniority": {
            "coverage": round(sum(1 for p in rows if seniority_of(p)) / n, 4) if n else 0.0,
            "min_group": MIN_SEN_N,
            "groups": sen_report,
        },
        "cooccurrence": co_rows[:20],
        "topics": {t: {"label": TOPICS[t]["label"], "count": topic[t],
                       "rate": round(topic[t] / n, 4) if n else 0.0} for t in TOPICS},
        "quote_samples": {a: quotes[a][:6] for a in AXES},
        "depth": {str(k): (round(v / n, 4) if n else 0.0) for k, v in sorted(depth.items())},
        "depth_counts": dict(sorted(depth.items())),
        "cohorts": cohorts,
        "fresh_vs_stale": fresh_vs_stale,
        "year_trend": year_trend,
        "month_trend": month_trend,
    }


SELFTEST_POS = {
    "runtime": "Build durable execution for long-running agents with checkpointing and resumable runs.",
    "harness": "Own the agentic harness: the tool-calling loop, planning, and multi-agent orchestration.",
    "context_memory": "Design context window management and long-term memory with a vector database.",
    "tool_mcp": "Expose tools through the Model Context Protocol; own tool schemas and function calling.",
    "sandbox_security": "Enforce scoped credentials and least privilege inside a sandboxed execution environment.",
    "control_plane": "Run the LLM gateway with model routing, rate limiting and token budget attribution.",
    "eval_gate": "Build the evaluation harness: offline eval, LLM-as-judge graders and regression gates.",
    "observability": "Own observability: distributed tracing, token-level logging and incident response.",
}
SELFTEST_POS_ZH = {
    "runtime": "负责 Agent Runtime 核心架构，包括长任务状态快照、断点恢复与执行引擎优化。",
    "harness": "建设通用 Agent Harness，支持 Agent Loop、多 Agent 编排与 Skill 体系插件化接入。",
    "context_memory": "建设上下文压缩、跨会话长期记忆与检索增强，持续优化 token 效率。",
    "tool_mcp": "设计工具调用的注册中心与 MCP 协议接入，完善插件机制与函数调用链路。",
    "sandbox_security": "完善沙箱隔离、权限边界、凭证注入回收与越权访问审计。",
    "control_plane": "建设模型网关与限流配额体系，围绕 token 成本与调度策略做优化。",
    "eval_gate": "建设任务评测集、自动评测与打分系统，完善版本回归门禁与轨迹反馈闭环。",
    "observability": "建设全链路可观测能力，覆盖链路追踪、Agent 事件流诊断与监控告警。",
}
SELFTEST_NEG = "Sell insurance policies to walk-in customers and manage the branch calendar."


def selftest() -> int:
    ok = True
    rows = []
    for axis, text in SELFTEST_POS.items():
        hits = axis_hits(clean_html(text), [{"text": text, "priority": "required"}])
        got = [a for a, h in hits.items() if h["body"]]
        if axis not in got:
            print(f"FAIL positive: axis {axis} not matched by its own sentence; matched={got}")
            ok = False
    for axis, text in SELFTEST_POS_ZH.items():
        hits = axis_hits(clean_html(text), [{"text": text, "priority": "required"}])
        got = [a for a, h in hits.items() if h["body"]]
        if axis not in got:
            print(f"FAIL positive-zh: axis {axis} not matched by its own Chinese sentence; matched={got}")
            ok = False
        if len(got) > 3:
            print(f"FAIL specificity-zh: one {axis} Chinese sentence lit {len(got)} axes {got}")
            ok = False
    neg = axis_hits(clean_html(SELFTEST_NEG), [{"text": SELFTEST_NEG, "priority": "required"}])
    got_neg = [a for a, h in neg.items() if h["body"]]
    if got_neg:
        print(f"FAIL negative: unrelated sentence matched {got_neg}")
        ok = False
    # A pattern set that matches everything would pass both above, so assert the
    # positive sentence for axis A does NOT light up all eight axes either.
    hits_all = axis_hits(clean_html(SELFTEST_POS["runtime"]), [{"text": SELFTEST_POS["runtime"], "priority": "required"}])
    lit = [a for a, h in hits_all.items() if h["body"]]
    if len(lit) > 3:
        print(f"FAIL specificity: one runtime sentence lit {len(lit)} axes {lit}")
        ok = False
    if title_family_selftest() != 0:
        ok = False
    if seniority_coverage_selftest() != 0:
        ok = False
    print("selftest: " + ("OK" if ok else "FAILED"))
    return 0 if ok else 1


def title_family_selftest() -> int:
    """The family split must classify both languages, and must not collapse.

    Guard against the failure this instrument already had once: an English-only
    title test labelled 64% of the Chinese slice "neither", which reads as
    "these posts are about nothing" instead of "my regexes speak one language".
    """
    ok = True
    cases = [
        ("Agent Platform Engineer", "ai_and_platform"),
        ("Senior Site Reliability Engineer", "platform_only"),
        ("LLM Engineer", "ai_only"),
        ("智能体平台研发工程师", "ai_and_platform"),
        ("大模型应用算法专家", "ai_only"),
        ("云平台架构师", "platform_only"),
        ("Account Executive", "neither"),
    ]
    for title, want in cases:
        got = title_family(title)
        if got != want:
            print(f"FAIL family: {title!r} -> {got}, want {want}")
            ok = False
    print("family selftest: " + ("OK" if ok else "FAILED"))
    return 0 if ok else 1


def seniority_coverage_selftest() -> int:
    """The seniority table must be built from the field that has data.

    Guard against the exact mistake this instrument made once: `seniority` at the
    top level is null on all 4017 rows while `enrichment.seniority` holds 1787
    values. A reader that trusts the top-level key returns an empty table that
    looks like "no data", which is indistinguishable from a real absence unless
    someone checks the other path.
    """
    sample = [{"seniority": None, "enrichment": {"seniority": "senior"},
               "description": "agent harness", "title": ""}]
    ok = seniority_of(sample[0]) == "senior"
    # And the negative: when the sub-object is genuinely absent, we must say so
    # instead of guessing from the title.
    blank = [{"seniority": "senior", "enrichment": {}, "description": "", "title": ""}]
    ok = ok and seniority_of(blank[0]) is None
    print("seniority selftest: " + ("OK" if ok else "FAILED "
                                    "(reads the null field instead of enrichment.seniority)"))
    return 0 if ok else 1


def prove_red() -> int:
    """Prove the selftest can fail: plant the two failure modes it exists for."""
    global COMPILED
    original = COMPILED
    failures = 0

    # 1. a matcher that matches nothing -> positive case must go red
    COMPILED = {k: re.compile(r"§NOMATCH§") for k in original}
    if selftest() == 0:
        print("FAIL: selftest stayed green when every axis pattern matched nothing")
        failures += 1
    else:
        print("ok: selftest goes red when patterns match nothing")

    # 2. a matcher that matches everything -> specificity case must go red
    COMPILED = {k: re.compile(r".") for k in original}
    if selftest() == 0:
        print("FAIL: selftest stayed green when every axis pattern matched everything")
        failures += 1
    else:
        print("ok: selftest goes red when patterns match everything")

    COMPILED = original

    # 3. an English-only title test on the Chinese slice -> the family table must
    # collapse into "neither". This is the shape of the error I actually made.
    global TITLE_AI, TITLE_PLATFORM
    _orig_ai, _orig_pl = TITLE_AI, TITLE_PLATFORM
    TITLE_AI = re.compile(r"agent|agentic|\bllm|ai engineer", re.I)
    TITLE_PLATFORM = re.compile(r"platform|infrastructure|sre\b", re.I)
    if title_family_selftest() == 0:
        print("FAIL: family selftest stayed green under an English-only title test")
        failures += 1
    else:
        print("ok: family selftest goes red when the title test is English-only")
    TITLE_AI, TITLE_PLATFORM = _orig_ai, _orig_pl

    # 4. read seniority from the TOP-LEVEL field, which is null on every row of
    # this corpus -> the seniority table must go empty AND the coverage selftest
    # must go red. This is the failure mode I actually hit: a "no seniority data
    # available" conclusion that was just reading the wrong key.
    global seniority_of
    _orig_read = seniority_of
    seniority_of = lambda p: p.get("seniority")  # noqa: E731
    rows = [{"enrichment": {"seniority": "senior"}, "description": "agent harness", "title": ""}]
    sen = analyze(rows)["seniority"]
    if sen["groups"]:
        print(f"FAIL: reading top-level seniority still produced {len(sen['groups'])} group(s)")
        failures += 1
    else:
        print("ok: reading top-level seniority yields an empty table (as it must)")
    if seniority_coverage_selftest() == 0:
        print("FAIL: seniority selftest stayed green while reading the null field")
        failures += 1
    else:
        print("ok: seniority selftest goes red when the wrong field is read")
    seniority_of = _orig_read
    if failures:
        print(f"prove_red: {failures} failure(s)")
        return 1
    print("prove_red: OK, selftest is falsifiable under all 4 injected violations")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--prove-red", action="store_true", dest="prove_red")
    ap.add_argument("--out", default=str(RAW / "axes_report.json"))
    ap.add_argument("--globs", default="enriched_a.json",
                    help="comma-separated enriched*.json names to read (dedupe by slug)")
    args = ap.parse_args()
    if args.prove_red:
        return prove_red()
    if args.selftest:
        return selftest()

    rows = load_corpus([g.strip() for g in args.globs.split(",") if g.strip()])
    if not rows:
        print("no enriched postings found", file=sys.stderr)
        return 2
    rep = analyze(rows)
    Path(args.out).write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"n_postings = {rep['n_postings']}\n")
    print(f"{'axis':18s} {'title':>7s} {'body':>7s} {'hidden':>7s} {'req':>5s} {'pref':>5s}")
    for a, v in rep["axes"].items():
        print(f"{a:18s} {v['title_rate']:7.1%} {v['body_rate']:7.1%} {v['hidden_rate']:7.1%} "
              f"{v['required_mentions']:5d} {v['preferred_mentions']:5d}")
    print("\naxes-per-posting (share):", {k: f"{v:.1%}" for k, v in rep["depth"].items()})
    print("\ncohorts:")
    for name, c in rep["cohorts"].items():
        top = sorted(c["axes"].items(), key=lambda kv: -kv[1])[:4]
        print(f"  {name:16s} n={c['n']:5d} mean_axes={c['mean_axes']:4.2f}  "
              + " ".join(f"{a}={v:.1%}" for a, v in top))
    print("\nfresh(<=90d) vs stale(>365d):")
    for a, v in rep["fresh_vs_stale"].items():
        f = v.get("fresh_90d", {}); st = v.get("stale_365d", {})
        if f and st:
            print(f"  {a:17s} fresh {f['rate']:6.1%} (n={f['n']:4d})   stale {st['rate']:6.1%} (n={st['n']:4d})")
    print("\nyear trend (body rate by posting year, n>=20):")
    years = sorted({y for v in rep["year_trend"].values() for y in v})
    hdr = "  " + f"{'axis':17s}" + "".join(f"{y:>10s}" for y in years)
    print(hdr)
    prev = None
    for a, v in rep["year_trend"].items():
        cells = []
        for y in years:
            if y not in v:
                cells.append(f"{'-':>10s}")
                continue
            rate = v[y]['rate']
            if prev is not None and y == years[-1]:
                arrow = "↑" if rate > prev + 0.02 else ("↓" if rate < prev - 0.02 else "=")
                cells.append(f"{rate:9.1%}{arrow}")
            else:
                cells.append(f"{rate:10.1%}")
            prev = rate
        print("  " + f"{a:22s}" + "".join(cells))
    mt = rep["month_trend"]
    if mt:
        months = sorted({m for v in mt.values() for m in v})
        print(f"\nmonth trend (n>={50} per cohort):")
        print("  " + f"{'axis':22s}" + "".join(f"{m[2:]:>8s}" for m in months) + f"{'Δ last-vs-first':>18s}")
        for a, v in mt.items():
            first = v[months[0]]['rate'] if months[0] in v else None
            last = v[months[-1]]['rate'] if months[-1] in v else None
            delta = f"{(last - first) * 100:+8.1f}pp" if (first is not None and last is not None) else " " * 18
            print("  " + f"{a:22s}" + "".join(f"{v[m]['rate']:8.1%}" if m in v else f"{'-':>8s}" for m in months) + f"{delta:>18s}")
    fams = rep.get("title_families") or {}
    if fams.get("groups"):
        order = ["ai_and_platform", "ai_only", "platform_only", "neither"]
        print(f"\ntitle families (AI-name x platform-name, n>={fams['min_group']}):")
        print("  " + f"{'family':18s}" + f"{'n':>6s}" + f"{'share':>8s}" +
              "".join(f"{a[:11]:>12s}" for a in AXES) + f"{'mean':>7s}")
        for fam in order:
            g = (fams["groups"] or {}).get(fam)
            if not g:
                continue
            print("  " + f"{fam:18s}" + f"{g['n']:6d}" + f"{g['share']:8.1%}" +
                  "".join(f"{g['axes'][a]:12.1%}" for a in AXES) +
                  f"{g['mean_axes']:7.2f}")

    sen = rep.get("seniority") or {}
    if sen.get("groups"):
        print(f"\nseniority (enrichment.seniority, coverage {sen['coverage']:.1%}, n>={sen['min_group']}):")
        svs = sorted(sen["groups"], key=lambda k: -sen["groups"][k]["n"])
        print("  " + f"{'level':12s}" + f"{'n':>6s}" + "".join(f"{a[:11]:>12s}" for a in AXES))
        for sv in svs:
            g = sen["groups"][sv]
            print("  " + f"{sv:12s}" + f"{g['n']:6d}" +
                  "".join(f"{g['axes'][a]:12.1%}" for a in AXES))

    print(f"\ntopics (rate over {rep['n_postings']}):")
    for t, v in rep["topics"].items():
        print(f"  {t:16s} {v['rate']:6.1%}  ({v['count']})")
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
