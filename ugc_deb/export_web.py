"""Export the database as compact JSON for the web prototype.

    python3 -m ugc_deb.export_web data/deb.sqlite out.json
    python3 -m ugc_deb.export_web data/deb.sqlite docs/index.html template_online.html
    python3 -m ugc_deb.export_web data/deb.sqlite docs/classic.html template.html
"""
import json
import re
import sqlite3
import sys
from pathlib import Path
from collections import Counter, defaultdict

from . import normalize as N


def _type(raw: str) -> str:
    t = raw.lower()
    for word, label in [("central", "Central University"), ("open", "State Open University"),
                        ("deemed", "Deemed to be University"), ("private", "Private University"),
                        ("state", "State University")]:
        if word in t:
            return label
    return ""


def _display(variants: Counter) -> str:
    # Prefer a mixed-case spelling without broken words; the source has "FOUNDATI ON" etc.
    def score(item):
        name, n = item
        return (any(c.islower() for c in name), n)
    name = max(variants.items(), key=score)[0]
    return name if any(c.islower() for c in name) else name.title()


def main(db, out, template="template.html"):
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    rows = [dict(r) for r in con.execute("SELECT * FROM programmes WHERE uni_key != ''")]
    meta = dict(con.execute("SELECT key, value FROM meta").fetchall())
    years = sorted({r["academic_year"] for r in rows})

    names, states, types = defaultdict(Counter), defaultdict(Counter), defaultdict(Counter)
    for r in rows:
        names[r["uni_key"]][r["name"]] += 1
        if r["state"]:
            states[r["uni_key"]][r["state"].strip().title()] += 1
        if _type(r["type"]):
            types[r["uni_key"]][_type(r["type"])] += 1
    keys = sorted(names, key=lambda k: _display(names[k]).lower())
    uidx = {k: i for i, k in enumerate(keys)}
    unis = [{
        "n": _display(names[k]),
        "k": k,
        "a": sorted({a for v in names[k] for a in N.university_acronyms(v)}),
        "s": states[k].most_common(1)[0][0] if states[k] else "",
        "t": types[k].most_common(1)[0][0] if types[k] else "",
    } for k in keys]

    progs, pidx, out_rows = [], {}, set()
    for r in rows:
        if not r["degree_code"]:
            continue
        p = pidx.setdefault(r["program_name"], len(progs))
        if p == len(progs):
            progs.append([re.sub(r"\s+", " ", r["program_name"]).strip(), r["degree_code"], r["specialisation"]])
        out_rows.add((uidx[r["uni_key"]], p, years.index(r["academic_year"]), 1 if r["mode_key"] == "ONLINE" else 0))

    data = {"asOf": meta.get("fetched_at"), "source": meta.get("source_url"), "years": years,
            "unis": unis, "progs": progs, "rows": sorted(out_rows)}
    payload = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
    if out.endswith(".html"):
        # Inline the data into the web prototype template.
        template = (Path(__file__).resolve().parent.parent / "web" / template).read_text()
        payload = template.replace("__DEB_DATA__", payload.replace("</", "<\\/"))
    Path(out).write_text(payload)
    print(f"{len(unis)} universities, {len(progs)} programmes, {len(out_rows)} rows")


if __name__ == "__main__":
    main(*sys.argv[1:4])
