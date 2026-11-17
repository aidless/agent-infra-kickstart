from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict

from .cost import DEFAULT_PRICE_ID, PRICING, cost_from_rates, rates_for
from .runner import create_session, default_plan, run_session
from .state import Store


def trace_cost_summary(store: Store, session_id: str) -> Dict[str, object]:
    """Aggregate cost from the trace file, recomputed rather than remembered.

    Nothing is stored twice: the total is a pure function of the rows, so a row
    edited by hand still produces a total that matches it — and a row whose
    cost_usd disagrees with its own tokens is reported as a mismatch instead of
    being silently summed.
    """
    path = store.trace_path(session_id)
    if not path.exists():
        return {"steps": 0, "tokens_in_est": 0, "tokens_out_est": 0, "cost_usd": 0.0, "mismatches": []}
    tot_in = tot_out = 0
    tot_cost = 0.0
    steps = 0
    mismatches = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("tokens_in_est") is None:
            continue
        steps += 1
        tot_in += row["tokens_in_est"]
        tot_out += row["tokens_out_est"]
        tot_cost += row["cost_usd"]
        recomputed = cost_from_rates(
            row["tokens_in_est"],
            row["tokens_out_est"],
            row.get("price_in_per_mtok", rates_for(DEFAULT_PRICE_ID)["in_per_mtok"]),
            row.get("price_out_per_mtok", rates_for(DEFAULT_PRICE_ID)["out_per_mtok"]),
        )
        if abs(recomputed - row["cost_usd"]) > 1e-12:
            mismatches.append({"step": row.get("step"), "row": row["cost_usd"], "recomputed": recomputed})
    return {
        "steps": steps,
        "tokens_in_est": tot_in,
        "tokens_out_est": tot_out,
        "cost_usd": tot_cost,
        "mismatches": mismatches,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Minimal Agent Infra demo (stateful, resumable, traced)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser("run", help="create and run a new session")
    p_run.add_argument("--goal", default="Analyze local inputs and produce a report")
    p_run.add_argument("--topic", default="Agent Infrastructure")
    p_run.add_argument("--input-dir", default="sample_input", help="directory to analyze (relative to cwd or absolute)")
    p_run.add_argument("--runs-dir", default="runs")
    p_run.add_argument("--fail-on-step", default=None, help="simulate failure at step name (demo)")
    p_run.add_argument("--max-retries", type=int, default=0)
    p_run.add_argument("--timeout-ms", type=int, default=None, help="per-step timeout budget in ms (all steps)")
    p_run.add_argument("--backoff-base-ms", type=int, default=0, help="exponential backoff base in ms (0 = no wait, schedule still recorded)")
    p_run.add_argument("--backoff-cap-ms", type=int, default=4000, help="backoff ceiling in ms")
    p_run.add_argument("--price-id", default=DEFAULT_PRICE_ID, choices=sorted(PRICING), help="local pricing fixture used for cost_usd")

    p_resume = sub.add_parser("resume", help="resume an existing session by id")
    p_resume.add_argument("session_id")
    p_resume.add_argument("--runs-dir", default="runs")
    p_resume.add_argument("--max-retries", type=int, default=0)
    p_resume.add_argument("--clear-timeouts", action="store_true", help="drop per-step timeout budgets before resuming")
    p_resume.add_argument("--backoff-base-ms", type=int, default=0)
    p_resume.add_argument("--backoff-cap-ms", type=int, default=4000)
    p_resume.add_argument("--price-id", default=DEFAULT_PRICE_ID, choices=sorted(PRICING))

    p_show = sub.add_parser("show", help="show session state")
    p_show.add_argument("session_id")
    p_show.add_argument("--runs-dir", default="runs")

    args = parser.parse_args()
    store = Store(Path(args.runs_dir))

    if args.cmd == "run":
        input_abs = str(Path(args.input_dir).resolve())
        session = create_session(store, args.goal, default_plan(args.topic, input_abs), input_dir=input_abs, topic=args.topic)
        if args.timeout_ms:
            for st in session.steps:
                st.timeout_ms = args.timeout_ms
        session = run_session(
            store,
            session,
            fail_on_step=args.fail_on_step,
            max_retries=args.max_retries,
            backoff_base_ms=args.backoff_base_ms,
            backoff_cap_ms=args.backoff_cap_ms,
            price_id=args.price_id,
        )
        print(json.dumps({
            "session_id": session.session_id,
            "status": session.status,
            "state": str(store.state_path(session.session_id)),
            "trace": str(store.trace_path(session.session_id)),
        }, ensure_ascii=False, indent=2))
        return

    if args.cmd == "resume":
        session = store.load(args.session_id)
        if args.clear_timeouts:
            for st in session.steps:
                st.timeout_ms = None
        session = run_session(
            store,
            session,
            max_retries=args.max_retries,
            backoff_base_ms=args.backoff_base_ms,
            backoff_cap_ms=args.backoff_cap_ms,
            price_id=args.price_id,
        )
        print(json.dumps({"session_id": session.session_id, "status": session.status}, ensure_ascii=False, indent=2))
        return

    if args.cmd == "show":
        session = store.load(args.session_id)
        print(json.dumps({**session.to_dict(), "cost": trace_cost_summary(store, session.session_id)}, ensure_ascii=False, indent=2))
        return


if __name__ == "__main__":
    main()
