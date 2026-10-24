from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from retailpulse.warehouse.build import build_and_export


def _repo_root() -> Path:
    # .../retailpulse/src/retailpulse/warehouse/__main__.py -> .../retailpulse
    return Path(__file__).resolve().parents[3]


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def cmd_build(_: argparse.Namespace) -> int:
    build_and_export(_repo_root())
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m retailpulse.warehouse")
    sub = p.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="build duckdb star schema + marts and export powerbi parquet")
    b.set_defaults(func=cmd_build)
    return p


def main(argv: list[str] | None = None) -> int:
    _configure_logging()
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
