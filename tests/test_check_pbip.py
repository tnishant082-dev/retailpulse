from __future__ import annotations

from pathlib import Path

from tools.check_pbip import check


def test_pbip_project_references_are_valid() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    pbip = repo_root / "dashboard" / "RetailPulse.pbip"
    failures = check(pbip)
    assert failures == []



def test_relationships_join_same_types() -> None:
    import sys

    import pytest

    repo_root = Path(__file__).resolve().parents[1]
    if not (repo_root / "data" / "powerbi" / "fact_sales.parquet").exists():
        pytest.skip("data/powerbi not built")
    sys.path.insert(0, str(repo_root / "tools"))
    import duckdb
    import generate_pbip

    assert generate_pbip.check_relationships(duckdb.connect()) == []
