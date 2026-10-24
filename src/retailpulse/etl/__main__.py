from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

from retailpulse.etl.clean import default_clean_path, run_clean
from retailpulse.etl.download import ensure_raw_online_retail_ii
from retailpulse.etl.quality import run_quality


def _repo_root() -> Path:
    # src/retailpulse/etl/__main__.py -> repo root
    return Path(__file__).resolve().parents[3]


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def cmd_run(_: argparse.Namespace) -> int:
    repo_root = _repo_root()
    xlsx_path = ensure_raw_online_retail_ii(repo_root)
    out_path = default_clean_path(repo_root)
    df_clean: pd.DataFrame = run_clean(xlsx_path=xlsx_path, out_path=out_path)
    failures = run_quality(df_clean)
    return 1 if failures else 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m retailpulse.etl")
    sub = p.add_subparsers(dest="cmd", required=True)
    run_p = sub.add_parser("run", help="download -> clean -> quality")
    run_p.set_defaults(func=cmd_run)
    return p


def main(argv: list[str] | None = None) -> int:
    _configure_logging()
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
