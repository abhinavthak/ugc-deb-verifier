"""CLI.

    python -m ugc_deb refresh                      # download + rebuild data/deb.sqlite
    python -m ugc_deb check -u "IGNOU" -p "MBA" -m online -y 2024
    python -m ugc_deb university "jain university"
"""
import argparse
import json
import sys
from pathlib import Path

from .scrape import refresh
from .verify import Verifier

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = ROOT / "data" / "deb.sqlite"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="ugc_deb")
    ap.add_argument("--db", type=Path, default=DEFAULT_DB)
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("refresh", help="download the DEB list and rebuild the database")
    r.add_argument("--html", type=Path, help="parse a saved copy of the page instead of downloading")

    c = sub.add_parser("check", help="check one degree")
    c.add_argument("-u", "--university", required=True)
    c.add_argument("-p", "--programme", required=True)
    c.add_argument("-m", "--mode", help="ODL or Online (omit to accept either)")
    c.add_argument("-y", "--year", required=True, help="enrolment year, e.g. 2023 or 2023-24")
    c.add_argument("-s", "--specialisation")

    u = sub.add_parser("university", help="look up how a university name resolves")
    u.add_argument("name")

    a = ap.parse_args(argv)
    if a.cmd == "refresh":
        n = refresh(a.db, snapshot_dir=a.db.parent / "snapshots", html_file=a.html)
        print(f"Loaded {n} rows into {a.db}")
        return 0

    v = Verifier(a.db)
    if a.cmd == "university":
        key, cands = v.resolve_university(a.name)
        print(json.dumps({"resolved": v.display.get(key), "candidates": cands}, indent=2))
        return 0

    result = v.check(a.university, a.programme, a.mode, a.year, a.specialisation)
    print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
    return 0 if result.verdict == "APPROVED" else 1


if __name__ == "__main__":
    sys.exit(main())
