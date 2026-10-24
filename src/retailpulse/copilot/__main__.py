from __future__ import annotations

import argparse
import sys

import uvicorn


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m retailpulse.copilot")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("serve", help="run the copilot API")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", default=8000, type=int)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.cmd == "serve":
        uvicorn.run("retailpulse.copilot.app:app", host=args.host, port=args.port, reload=False)
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
