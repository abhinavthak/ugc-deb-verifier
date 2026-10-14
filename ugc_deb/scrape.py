"""Download the UGC-DEB programme list and load it into SQLite.

The page (https://deb.ugc.ac.in/Home/HEI_Prog_List) is a single ~11 MB
server-rendered HTML table with no API. Each refresh stores a dated raw
snapshot next to the database so past states can be audited.
"""
from __future__ import annotations

import datetime as dt
import gzip
import html
import re
import sqlite3
import urllib.request
from pathlib import Path

from . import normalize as N

SOURCE_URL = "https://deb.ugc.ac.in/Home/HEI_Prog_List"
COLUMNS = ["sr_no", "year", "session", "mode", "name", "type", "state", "program_name", "level"]


def fetch(url: str = SOURCE_URL, timeout: int = 120) -> str:
    req = urllib.request.Request(url, headers={
        "User-Agent": "ugc-deb-verifier/0.1 (degree approval lookup)",
        "Accept-Encoding": "gzip",
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read()
        if resp.headers.get("Content-Encoding") == "gzip":
            body = gzip.decompress(body)
    return body.decode("utf-8", errors="replace")


def _cell(c: str) -> str:
    return html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", c))).strip()


def parse(page: str) -> list[dict]:
    """Return one dict per row of the programme table."""
    for table in re.findall(r"<table.*?</table>", page, re.S | re.I):
        headers = [_cell(h).lower() for h in re.findall(r"<th[^>]*>(.*?)</th>", table, re.S | re.I)]
        if "program name" not in headers:
            continue
        if len(headers) != len(COLUMNS):
            raise ValueError(f"Unexpected table headers, source layout changed: {headers}")
        rows = []
        for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", table, re.S | re.I):
            cells = [_cell(c) for c in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S | re.I)]
            if len(cells) == len(COLUMNS):
                rows.append(dict(zip(COLUMNS, cells)))
        return rows
    raise ValueError("Programme table not found on page; source layout changed")


def enrich(row: dict) -> dict:
    code, spec, hons = N.split_programme(row["program_name"])
    return {
        **row,
        "uni_key": N.university_key(row["name"]),
        "mode_key": N.mode_key(row["mode"]),
        "academic_year": N.academic_year(row["year"]),
        "degree_code": code,
        "specialisation": spec,
        "hons": int(hons),
    }


SCHEMA = """
CREATE TABLE IF NOT EXISTS programmes (
    id INTEGER PRIMARY KEY,
    sr_no TEXT, year TEXT, session TEXT, mode TEXT, name TEXT, type TEXT,
    state TEXT, program_name TEXT, level TEXT,
    uni_key TEXT, mode_key TEXT, academic_year TEXT,
    degree_code TEXT, specialisation TEXT, hons INTEGER
);
CREATE INDEX IF NOT EXISTS ix_uni ON programmes(uni_key, academic_year);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
"""


def build_db(rows: list[dict], db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = db_path.with_suffix(".tmp")
    tmp.unlink(missing_ok=True)
    con = sqlite3.connect(tmp)
    con.executescript(SCHEMA)
    enriched = [enrich(r) for r in rows]
    cols = list(enriched[0].keys())
    con.executemany(
        f"INSERT INTO programmes ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
        [tuple(r[c] for c in cols) for r in enriched],
    )
    con.executemany("INSERT INTO meta VALUES (?, ?)", [
        ("source_url", SOURCE_URL),
        ("fetched_at", dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")),
        ("row_count", str(len(enriched))),
    ])
    con.commit()
    con.close()
    tmp.replace(db_path)  # atomic swap so readers never see a half-built DB


def refresh(db_path: Path, snapshot_dir: Path | None = None, html_file: Path | None = None) -> int:
    page = html_file.read_text(encoding="utf-8", errors="replace") if html_file else fetch()
    rows = parse(page)
    if len(rows) < 1000:
        raise ValueError(f"Only {len(rows)} rows parsed; refusing to replace the database")
    if snapshot_dir and not html_file:
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        stamp = dt.date.today().isoformat()
        with gzip.open(snapshot_dir / f"HEI_Prog_List_{stamp}.html.gz", "wt", encoding="utf-8") as f:
            f.write(page)
    build_db(rows, db_path)
    return len(rows)
