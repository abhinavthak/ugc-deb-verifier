# ugc-deb-verifier

Answers one question: **was University X approved by UGC-DEB to run Programme Y in mode Z
(ODL / Online) for the academic year the student enrolled?**

Source: <https://deb.ugc.ac.in/Home/HEI_Prog_List> (one ~11 MB HTML table, no API,
2020-21 onward). Python 3.9+, standard library only.

**Live checker (online degrees):** <https://abhinavthak.github.io/ugc-deb-verifier/>
· full ODL + Online version: <https://abhinavthak.github.io/ugc-deb-verifier/classic.html>

## Web pages

The pages in `docs/` are static, with the UGC data inlined, and are served by GitHub Pages.
They're built from the templates in `web/`:

```bash
python3 -m ugc_deb refresh
python3 -m ugc_deb.export_web data/deb.sqlite docs/index.html template_online.html
python3 -m ugc_deb.export_web data/deb.sqlite docs/classic.html template.html
```

The pages carry a JavaScript copy of the matching rules in `verify.py`; keep the two in step.
The lead form on the online page is a prototype and doesn't send data anywhere yet.

## Usage

```bash
python3 -m ugc_deb refresh          # download + rebuild data/deb.sqlite (+ dated snapshot)
python3 -m ugc_deb check -u "IGNOU" -p "MBA (Marketing)" -m odl -y 2025
python3 -m ugc_deb university "jain deemed university"   # see how a name resolves
python3 -m unittest                 # tests (fixture data, no network)
```

```python
from ugc_deb.verify import Verifier
v = Verifier("data/deb.sqlite")          # load once, reuse; ~14k rows in memory
r = v.check("Guru Ghasidas Vishwavidyalaya", "MA English", "online", "2026")
r.verdict, r.reason, r.detail, r.matched_records, r.approval_history
```

`year` is the **enrolment** year: `2023` and `2023-24` both mean academic year 2023-24.
`mode` may be omitted to accept either mode.

## Verdicts

| verdict | reason | meaning |
|---|---|---|
| `APPROVED` | `MATCH` | University, degree, specialisation, mode and year all match a listed entry |
| `NEEDS_REVIEW` | `BASE_DEGREE_ONLY` | Degree approved that year/mode but listed without specialisations, so the one asked about can't be confirmed |
| `NEEDS_REVIEW` | `UNIVERSITY_NOT_LISTED_FOR_YEAR` | University has **no entries at all** that year. The list has gaps (e.g. IGNOU only appears from 2025-26), so this is not a rejection |
| `NOT_APPROVED` | `WRONG_MODE` | Approved that year, but only in the other mode |
| `NOT_APPROVED` | `YEAR_NOT_APPROVED` | University listed that year; this programme approved only in other years |
| `NOT_APPROVED` | `SPECIALISATION_NOT_APPROVED` | Degree exists, specialisation never listed |
| `NOT_APPROVED` | `PROGRAMME_NEVER_APPROVED` | University never had this degree in any year |
| `NOT_APPROVED` | `NOT_OFFERED_VIA_ODL_ONLINE` | B.Tech, MBBS, LLB, B.Pharm, nursing etc. never appear in the DEB scheme |
| `UNIVERSITY_NOT_FOUND` | `NOT_IN_DEB_LIST` | No institution by that name in any year |
| `UNIVERSITY_AMBIGUOUS` | `CONFIRM_UNIVERSITY` | Close but not exact match; `university_candidates` lists options |
| `OUT_OF_COVERAGE` | `YEAR_OUTSIDE_DATA` | Year before 2020-21 or after the latest year in the list |
| `INVALID_INPUT` | `BAD_YEAR` / `BAD_MODE` / `UNKNOWN_DEGREE` | Couldn't parse the input |

## How matching works

- **University**: case, punctuation, stray spaces ("FOUNDATI ON"), "(Deemed to be University)" and
  "Univ" are normalised away; acronyms from the source (`(TNOU)`) and a small alias table (`ALIASES`
  in `verify.py`: IGNOU, LPU, …) are recognised; typos are fuzzy-matched on the distinctive part of the
  name. Partial names ("Manipal University Jaipur" vs "Manipal University") return candidates instead
  of guessing.
- **Programme**: split into a canonical degree code (`DEGREES` in `normalize.py`, typo-tolerant) and a
  specialisation. A specialisation matches if all its words appear in the listed one, so "Finance"
  matches "MBA (HR/MARKETING/FINANCE)".
- **Mode**: every source label collapses to `ODL` or `ONLINE`.

## Known limits

- The list starts in 2020-21; earlier enrolments need older DEB recognition notices.
- Some universities are missing for whole years; see `UNIVERSITY_NOT_LISTED_FOR_YEAR`.
- 30 rows in 2026-27 have no university name in the source and are ignored.
- This checks programme **approval**, not whether a specific certificate is genuine.
- Re-run `refresh` periodically (new sessions are added); the parser refuses to replace the DB if the
  page layout changes or fewer than 1,000 rows parse.
