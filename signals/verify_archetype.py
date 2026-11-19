#!/usr/bin/env python3
"""Cross-check the core finding — "the eight axes are the infrastructure side of
AI jobs, not the AI upgrade of infra jobs" — against a source INDEPENDENT of our
hand-built title regex: freehire's own `ai_archetype` classifier.

The title-family split in analyze_axes.py is OUR regex. If it were wrong, the
whole finding would be an artifact of that regex. This gate re-tests the same
proposition using the platform's own classifier, with pre-registered verdicts.

PRE-REGISTERED VERDICTS (written before fetching; do not tune after seeing data):
  P1  ai-builder side (agent_builder + fullstack_ai_engineer) has a higher
      body-hit rate on context_memory/tool_mcp than platform-ml side
      (cloud_ml_platform_engineer + devops_infra_engineer), gap >= 0.10.
  P2  platform-ml side has a higher body-hit rate on runtime/control_plane than
      ai-builder side, gap >= 0.05.
  P3  junior share (from facets seniority) on the ai-builder side is >= the
      platform-ml side (AI jobs are more entry-level accessible).

POST-HOC CORRECTION (2026-11-18, evidence-driven, direction = stricter):
  The original P2 assumed a NON-AI infra control group. That premise is FALSE:
  all 6 archetypes are AI roles (AI-word hit 95-100% of samples). Worse,
  agent_builder and rag_app_builder hit context_memory on 100% of samples,
  proving the platform classifier is CO-LINEAR with our 8-axis regex — it is
  the SAME instrument cut a different way, not an independent source. A
  circular instrument cannot verify the finding. We do NOT lower P2's threshold
  to make it green; we add a circularity guard that refuses to issue a verdict
  (NOT RUN) when any archetype's context_memory rate >= 0.95, and record P2's
  premise failure as a finding. This makes the gate stricter, not looser.

Exit codes: 0 = all pre-registered verdicts supported; 1 = at least one
contradicted (or a trivial/empty instrument); 2 = usage; 3 = not run
(insufficient samples / archetpe collapse). "Not run" wording includes
"not run is not a pass".

Summary first line always carries problems=N plus every verdict + sample size.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
RAW = HERE / "raw"
SAMPLES = RAW / "archetype_samples.json"
FACETS = HERE / "archetype_facets.json"
sys.path.insert(0, str(HERE))
import analyze_axes as ax  # noqa: E402  reuse the exact 8-axis vocabulary

API = "https://freehire.me/api/v1/agent/jobs/search"
FACETS_API = "https://freehire.me/api/v1/jobs/facets"
UA = {"User-Agent": "Mozilla/5.0 (archetype-crosscheck; research)"}

ARCHETYPES = [
    "agent_builder",
    "fullstack_ai_engineer",
    "rag_app_builder",
    "cloud_ml_platform_engineer",
    "devops_infra_engineer",
    "ml_trainer_researcher",
]
AI_SIDE = ["agent_builder", "fullstack_ai_engineer"]
INFRA_SIDE = ["cloud_ml_platform_engineer", "devops_infra_engineer"]
P1_AXES = ["context_memory", "tool_mcp"]
P2_AXES = ["runtime", "control_plane"]

# Pre-registered thresholds — never loosen these to make a verdict pass.
P1_MIN_GAP = 0.10
P2_MIN_GAP = 0.05
MIN_PER_ARCH = 60          # below this a rate is noise -> NOT_RUN
TRIVIAL_RATE = 0.99        # a body-hit rate >= this means the instrument is broken
CIRCULAR_RATE = 0.95       # an archetype with context_memory >= this is co-linear
                           # with our axis regex -> not an independent source


def _get(url: str, timeout: int = 30) -> dict:
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers=UA)
            return json.load(urllib.request.urlopen(req, timeout=timeout))
        except Exception:
            if attempt == 2:
                raise
            time.sleep(1.5 * (attempt + 1))


def fetch() -> int:
    """Fetch descriptions (for the 8-axis body check) and facets (for seniority)."""
    RAW.mkdir(parents=True, exist_ok=True)
    samples: dict[str, list[dict]] = {}
    for arch in ARCHETYPES:
        rows: list[dict] = []
        for page in (1, 2, 3):
            q = urllib.parse.urlencode({"ai_archetype": arch, "limit": 100, "page": page})
            d = _get(f"{API}?{q}")
            batch = d.get("data") or []
            if not batch:
                break
            for r in batch:
                rows.append({
                    "slug": r.get("public_slug"),
                    "title": r.get("title"),
                    "description_html": r.get("description") or "",
                })
            if len(batch) < 100:
                break
        samples[arch] = rows
        print(f"fetched {arch}: {len(rows)}")
    SAMPLES.write_text(json.dumps(samples, ensure_ascii=False), encoding="utf-8")

    facets: dict[str, dict] = {}
    for arch in ARCHETYPES:
        d = _get(f"{FACETS_API}?ai_archetype={urllib.parse.quote(arch)}")
        facets[arch] = d["data"]["facets"]
        print(f"facets {arch}: total={d['data']['total']}")
    FACETS.write_text(json.dumps(facets, ensure_ascii=False), encoding="utf-8")
    return 0


def load() -> tuple[dict, dict]:
    if not SAMPLES.exists() or not FACETS.exists():
        raise FileNotFoundError("run --fetch first")
    return (json.loads(SAMPLES.read_text(encoding="utf-8")),
            json.loads(FACETS.read_text(encoding="utf-8")))


def _rate(samples: dict, archs: list[str], axes: list[str], *, body_override=None) -> dict[str, float]:
    """Body-hit rate per axis over the union of the given archetypes' samples."""
    rows = [r for a in archs for r in samples.get(a, [])]
    if not rows:
        return {a: 0.0 for a in axes}
    hits = {a: 0 for a in axes}
    for r in rows:
        body = ax.clean_html(r["description_html"]) if body_override is None else body_override(r)
        for a in axes:
            if ax.COMPILED[a].search(body):
                hits[a] += 1
    return {a: hits[a] / len(rows) for a in axes}


def _senior_share(facets: dict, archs: list[str]) -> float:
    """junior postings / all seniority-tagged postings, over the given archetypes."""
    jr = tot = 0
    for a in archs:
        sen = (facets.get(a) or {}).get("seniority") or {}
        jr += int(sen.get("junior", 0))
        tot += sum(int(v) for v in sen.values())
    return jr / tot if tot else 0.0


def evaluate(samples: dict, facets: dict, *, body_override=None, collapse=False,
             disable_circularity=False) -> dict:
    """Return machine-readable verdicts. `collapse` simulates a dead classifier;
    `disable_circularity` exists ONLY for prove_red, to show the guard is the
    thing preventing a false green on the circular corpus."""
    archs = list(ARCHETYPES)
    if collapse:
        # simulate the classifier labelling everything as one archetype
        samples = {"agent_builder": [r for a in ARCHETYPES for r in samples.get(a, [])]}
        ai_sample, infra_sample = ["agent_builder"], ["agent_builder"]
        facets = {"agent_builder": {}}
    else:
        ai_sample, infra_sample = AI_SIDE, INFRA_SIDE

    sizes = {a: len(samples.get(a, [])) for a in ARCHETYPES}
    if collapse:
        enough = False
    else:
        enough = all(sizes.get(a, 0) >= MIN_PER_ARCH for a in AI_SIDE + INFRA_SIDE)

    ai_p1 = _rate(samples, ai_sample, P1_AXES, body_override=body_override)
    infra_p1 = _rate(samples, infra_sample, P1_AXES, body_override=body_override)
    ai_p2 = _rate(samples, ai_sample, P2_AXES, body_override=body_override)
    infra_p2 = _rate(samples, infra_sample, P2_AXES, body_override=body_override)

    p1_gap = sum(ai_p1.values()) / len(P1_AXES) - sum(infra_p1.values()) / len(P1_AXES)
    p2_gap = sum(infra_p2.values()) / len(P2_AXES) - sum(ai_p2.values()) / len(P2_AXES)

    trivial = any(v >= TRIVIAL_RATE for v in list(ai_p1.values()) + list(infra_p1.values())
                  + list(ai_p2.values()) + list(infra_p2.values()))

    # Circularity guard: if ANY SINGLE archetype's context_memory rate is
    # >= CIRCULAR_RATE, the platform classifier is co-linear with our axis regex
    # -> it cannot serve as an independent source. Measure PER archetype and take
    # the MAX: pooling all rows dilutes a 100% archetype down to ~59% and would
    # hide the circularity — the exact defect this guard exists to catch.
    per_arch_cm = {a: _rate(samples, [a], ["context_memory"])["context_memory"]
                   for a in samples}
    max_cm = max(per_arch_cm.values()) if per_arch_cm else 0.0
    circular = (not disable_circularity) and max_cm >= CIRCULAR_RATE

    ai_jr = _senior_share(facets, ai_sample)
    infra_jr = _senior_share(facets, infra_sample)

    # A circular or trivial instrument issues NO verdict — "not run is not a pass".
    if circular or trivial or not enough:
        p1 = p2 = p3 = "NOT_RUN"
    else:
        p1 = "SUPPORTED" if p1_gap >= P1_MIN_GAP else "CONTRADICTED"
        p2 = "SUPPORTED" if p2_gap >= P2_MIN_GAP else "CONTRADICTED"
        p3 = "SUPPORTED" if ai_jr >= infra_jr else "CONTRADICTED"

    return {
        "enough_samples": enough,
        "trivial_instrument": trivial,
        "circular_instrument": circular,
        "max_archetype_context_memory_rate": round(max_cm, 4),
        "per_archetype_context_memory": {a: round(v, 4) for a, v in per_arch_cm.items()},
        "p2_premise_nonai_control": False,  # all 6 archetypes are AI roles (measured post-hoc)
        "sizes": sizes,
        "ai_p1": ai_p1, "infra_p1": infra_p1, "p1_gap": round(p1_gap, 4), "p1": p1,
        "ai_p2": ai_p2, "infra_p2": infra_p2, "p2_gap": round(p2_gap, 4), "p2": p2,
        "ai_junior_share": round(ai_jr, 4), "infra_junior_share": round(infra_jr, 4), "p3": p3,
        "p1_min_gap": P1_MIN_GAP, "p2_min_gap": P2_MIN_GAP, "min_per_arch": MIN_PER_ARCH,
    }


def prove_red(samples: dict, facets: dict) -> int:
    """Non-emptiness: each detector must be shown to be the thing that stops a
    false verdict. Three injections, each must flip the gate's outcome.

    Baseline on the real corpus is NOT_RUN (circular source). This is the
    correct outcome, not a green. We prove the guard is load-bearing by
    disabling it and showing a false SUPPORTED appears on the SAME data.
    """
    problems = 0

    real = evaluate(samples, facets)
    print(f"baseline: state={'NOT_RUN' if real['circular_instrument'] else 'EVALUATED'} "
          f"circular={real['circular_instrument']} p1={real['p1']} p2={real['p2']} p3={real['p3']}")
    if not real["circular_instrument"] or real["p1"] != "NOT_RUN":
        print("FAIL prove_red setup: real corpus should be NOT_RUN (circular)")
        return 1

    # [1/3] disable circularity guard -> a FALSE green appears on the same data.
    # This proves the guard is the only thing preventing a circular false pass.
    unguarded = evaluate(samples, facets, disable_circularity=True)
    if unguarded["p1"] != "SUPPORTED" or unguarded["circular_instrument"]:
        print(f"FAIL prove_red[1/3] guard-removal: expected false SUPPORTED, got p1={unguarded['p1']} circular={unguarded['circular_instrument']}")
        problems += 1
    else:
        print("OK prove_red[1/3] guard-removal: without circularity guard, circular data yields FALSE SUPPORTED")

    # [2/3] classifier collapse (all rows one archetype) -> NOT_RUN
    collapse = evaluate(samples, facets, collapse=True)
    if collapse["enough_samples"] or collapse["p1"] == "SUPPORTED":
        print(f"FAIL prove_red[2/3] collapse: gate should not pass, got enough={collapse['enough_samples']} p1={collapse['p1']}")
        problems += 1
    else:
        print("OK prove_red[2/3] collapse: gate refuses (not run is not a pass)")

    # [3/3] trivial instrument: every body hits every axis -> rate ~1.0
    trivial = evaluate(samples, facets, body_override=lambda r: "context memory tool mcp runtime control plane harness")
    if not (trivial["trivial_instrument"] or trivial["circular_instrument"]) or trivial["p1"] == "SUPPORTED":
        print(f"FAIL prove_red[3/3] trivial: gate should flag broken instrument, got trivial={trivial['trivial_instrument']} circular={trivial['circular_instrument']} p1={trivial['p1']}")
        problems += 1
    else:
        print("OK prove_red[3/3] trivial instrument: gate flags it, verdict not pass")

    if problems:
        print(f"prove_red: FAILED ({problems}/3 injections did not turn it red)")
        return 1
    print("prove_red: OK, crosscheck gate goes red under all 3 injected violations")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--fetch", action="store_true", help="fetch samples + facets from freehire")
    ap.add_argument("--prove-red", action="store_true", help="run 3 injected-violation checks")
    args = ap.parse_args()

    if args.fetch:
        return fetch()

    samples, facets = load()
    if args.prove_red:
        return prove_red(samples, facets)

    v = evaluate(samples, facets)
    n = sum(v["sizes"].values())
    not_run = (v["circular_instrument"] or v["trivial_instrument"]
               or not v["enough_samples"])
    # "problems" here counts verdict-level contradictions among the verdicts
    # that were actually ISSUED (NOT_RUN is the third state, not a contradiction).
    problems = sum(1 for k in ("p1", "p2", "p3") if v[k] == "CONTRADICTED")
    # summary FIRST line carries problems=N, state, every verdict + sample size
    print(f"problems={problems} state={'NOT_RUN' if not_run else 'EVALUATED'} "
          f"p1={v['p1']} p2={v['p2']} p3={v['p3']} "
          f"archetypes={len([a for a in ARCHETYPES if v['sizes'].get(a,0)])} n={n} "
          f"circular={v['circular_instrument']} max_cm={v['max_archetype_context_memory_rate']} "
          f"trivial={v['trivial_instrument']} enough={v['enough_samples']}")
    print(json.dumps(v, ensure_ascii=False, indent=2))
    if not_run:
        reason = ("circular source (ai_archetype co-linear with axis regex)" if v["circular_instrument"]
                  else "trivial instrument" if v["trivial_instrument"]
                  else "insufficient samples")
        print(f"VERDICT: NOT RUN — {reason}; not run is not a pass")
        return 3
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
