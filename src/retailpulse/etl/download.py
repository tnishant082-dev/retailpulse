from __future__ import annotations

import logging
import zipfile
from pathlib import Path

import requests

log = logging.getLogger(__name__)

UCI_ZIP_URL = "https://archive.ics.uci.edu/static/public/502/online+retail+ii.zip"
ZIP_FILENAME = "online+retail+ii.zip"


def default_raw_dir(repo_root: Path) -> Path:
    return repo_root / "data" / "raw"


def download_online_retail_ii_zip(raw_dir: Path) -> Path:
    raw_dir.mkdir(parents=True, exist_ok=True)
    zip_path = raw_dir / ZIP_FILENAME
    if zip_path.exists():
        log.info("Zip already exists, skipping download: %s", zip_path)
        return zip_path

    log.info("Downloading %s -> %s", UCI_ZIP_URL, zip_path)
    with requests.get(UCI_ZIP_URL, stream=True, timeout=60) as r:
        r.raise_for_status()
        with zip_path.open("wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    f.write(chunk)

    return zip_path


def _safe_extract(member: zipfile.ZipInfo, *, dest_dir: Path) -> Path:
    # Prevent zip-slip by verifying the resolved destination stays within dest_dir.
    target = (dest_dir / member.filename).resolve()
    if dest_dir.resolve() not in target.parents and target != dest_dir.resolve():
        msg = f"Unsafe zip member path: {member.filename}"
        raise ValueError(msg)
    return target


def extract_xlsx(zip_path: Path, raw_dir: Path) -> list[Path]:
    raw_dir.mkdir(parents=True, exist_ok=True)
    extracted: list[Path] = []

    with zipfile.ZipFile(zip_path) as zf:
        xlsx_members = [m for m in zf.infolist() if m.filename.lower().endswith(".xlsx")]
        if not xlsx_members:
            msg = f"No .xlsx found inside {zip_path}"
            raise FileNotFoundError(msg)

        for member in xlsx_members:
            out_path = _safe_extract(member, dest_dir=raw_dir)
            if out_path.exists():
                log.info("XLSX already exists, skipping extract: %s", out_path)
                extracted.append(out_path)
                continue

            out_path.parent.mkdir(parents=True, exist_ok=True)
            log.info("Extracting %s -> %s", member.filename, out_path)
            with zf.open(member, "r") as src, out_path.open("wb") as dst:
                dst.write(src.read())
            extracted.append(out_path)

    return extracted


def ensure_raw_online_retail_ii(repo_root: Path) -> Path:
    raw_dir = default_raw_dir(repo_root)
    zip_path = download_online_retail_ii_zip(raw_dir)
    xlsx_paths = extract_xlsx(zip_path, raw_dir)

    # Prefer a top-level xlsx if present; otherwise just take the first.
    xlsx_paths_sorted = sorted(xlsx_paths, key=lambda p: (len(p.parts), p.name))
    xlsx_path = xlsx_paths_sorted[0]
    log.info("Using xlsx: %s", xlsx_path)
    return xlsx_path
