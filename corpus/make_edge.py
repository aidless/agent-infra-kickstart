"""Regenerate the generated parts of corpus/edge.

The small text fixtures are checked in as real files; the large file is generated
so the repo does not carry 700 KB of filler. Run this once after a fresh clone:

    python3 corpus/make_edge.py
"""
from __future__ import annotations

from pathlib import Path

HERE = Path(__file__).resolve().parent


def main() -> None:
    edge = HERE / "edge"
    edge.mkdir(parents=True, exist_ok=True)
    target = edge / "large.txt"
    target.write_text(
        "\n".join(f"line {i} agent infra reliability" for i in range(20000)),
        encoding="utf-8",
    )
    print(f"wrote {target} ({target.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
