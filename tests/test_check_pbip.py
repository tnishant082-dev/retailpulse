from __future__ import annotations

from pathlib import Path

from tools.check_pbip import check


def test_pbip_project_references_are_valid() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    pbip = repo_root / "dashboard" / "RetailPulse.pbip"
    failures = check(pbip)
    assert failures == []

