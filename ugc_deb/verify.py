"""Answer: was University X approved by UGC-DEB to run Programme Y in mode Z
for the academic year the student enrolled?
"""
from __future__ import annotations

import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass, field, asdict
from pathlib import Path

from . import normalize as N

# Common short names that do not appear in the source data itself.
# Values are full names; they are turned into keys at load time.
ALIASES = {
    "ignou": "Indira Gandhi National Open University",
    "lpu": "Lovely Professional University",
    "smu": "Sikkim Manipal University",
    "ycmou": "Yashwantrao Chavan Maharashtra Open University",
    "ksou": "Karnataka State Open University",
    "tnou": "Tamil Nadu Open University",
    "uou": "Uttarakhand Open University",
    "nou": "Nalanda Open University",
    "baou": "Dr. Babasaheb Ambedkar Open University",
    "vmou": "Vardhman Mahaveer Open University",
    "mpbou": "M.P. Bhoj (Open) University",
    "netaji subhas open university": "Netaji Subhas Open University",
    "nsou": "Netaji Subhas Open University",
    "kl university": "Koneru Lakshmaiah Education Foundation",
    "dypatil": "Dr. D.Y. Patil Vidyapeeth",
    "sndt": "Smt. Nathibai Damodar Thackersey Women's University",
    "dei": "Dayal Bagh Educational Institute",
    "gla": "G.L.A. University",
}

# Verdicts
APPROVED = "APPROVED"
NEEDS_REVIEW = "NEEDS_REVIEW"
NOT_APPROVED = "NOT_APPROVED"
UNIVERSITY_NOT_FOUND = "UNIVERSITY_NOT_FOUND"
UNIVERSITY_AMBIGUOUS = "UNIVERSITY_AMBIGUOUS"
OUT_OF_COVERAGE = "OUT_OF_COVERAGE"
INVALID_INPUT = "INVALID_INPUT"


@dataclass
class Result:
    verdict: str
    reason: str
    detail: str
    query: dict
    university: str | None = None
    university_candidates: list = field(default_factory=list)
    matched_records: list = field(default_factory=list)
    approval_history: dict = field(default_factory=dict)  # academic_year -> [modes] for this programme
    data_as_of: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


class Verifier:
    def __init__(self, db_path: Path | str):
        con = sqlite3.connect(db_path)
        con.row_factory = sqlite3.Row
        self.rows = [dict(r) for r in con.execute("SELECT * FROM programmes")]
        self.meta = dict(con.execute("SELECT key, value FROM meta").fetchall())
        con.close()

        self.by_uni: dict[str, list[dict]] = defaultdict(list)
        names: dict[str, Counter] = defaultdict(Counter)
        self.acronyms: dict[str, set[str]] = defaultdict(set)
        for r in self.rows:
            if not r["uni_key"]:  # a few source rows have no institution name
                continue
            self.by_uni[r["uni_key"]].append(r)
            names[r["uni_key"]][r["name"]] += 1
            for a in N.university_acronyms(r["name"]):
                self.acronyms[a].add(r["uni_key"])
        self.display = {k: c.most_common(1)[0][0] for k, c in names.items()}
        for alias, full in ALIASES.items():
            key = N.university_key(full)
            if key in self.by_uni:
                self.acronyms[N.squash(alias)].add(key)
        years = sorted({r["academic_year"] for r in self.rows if r["academic_year"]})
        self.first_year, self.last_year = years[0], years[-1]

    # ------------------------------------------------------------ universities

    def resolve_university(self, query: str) -> tuple[str | None, list[dict]]:
        """Return (uni_key or None, ranked candidates)."""
        k = N.university_key(query)
        if not k:
            return None, []
        if k in self.by_uni:
            return k, [self._cand(k, 1.0)]
        hits = self.acronyms.get(N.squash(query))
        if hits and len(hits) == 1:
            key = next(iter(hits))
            return key, [self._cand(key, 1.0)]

        qc = N.university_core(k)
        scored = []
        for key in self.by_uni:
            kc = N.university_core(key)
            sc = 1.0 if qc and qc == kc else N.similarity(qc, kc)
            # "Amity" should surface "Amity University Uttar Pradesh" etc., but only as a
            # candidate: "Manipal University Jaipur" is not "Manipal University".
            if len(qc) >= 4 and kc and (qc in kc or kc in qc):
                sc = max(sc, 0.85)
            if sc >= 0.8:
                scored.append((sc, key))
        scored.sort(reverse=True)
        cands = [self._cand(key, sc) for sc, key in scored[:5]]
        if not scored:
            return None, []
        best_sc, best = scored[0]
        clear_winner = len(scored) == 1 or best_sc - scored[1][0] >= 0.05
        if best_sc >= 0.9 and clear_winner:
            return best, cands
        return None, cands

    def _cand(self, key: str, score: float) -> dict:
        r0 = self.by_uni[key][0]
        return {"name": self.display[key], "state": r0["state"], "score": round(score, 3)}

    # --------------------------------------------------------------- the check

    def check(self, university: str, programme: str, mode: str | None, year,
              specialisation: str | None = None) -> Result:
        q_year = N.academic_year(year)
        q_mode = N.mode_key(mode) if mode else None
        code, q_spec, _ = N.split_programme(programme)
        if specialisation:
            q_spec = N._clean_spec(specialisation)
        query = {"university": university, "programme": programme, "mode": mode, "year": year,
                 "specialisation": specialisation,
                 "normalised": {"degree": code, "specialisation": q_spec, "mode": q_mode,
                                "academic_year": q_year}}
        res = lambda verdict, reason, detail, **kw: Result(
            verdict, reason, detail, query, data_as_of=self.meta.get("fetched_at"), **kw)

        if not q_year:
            return res(INVALID_INPUT, "BAD_YEAR", f"Could not read enrolment year {year!r}; use e.g. 2023 or 2023-24.")
        if mode and not q_mode:
            return res(INVALID_INPUT, "BAD_MODE", f"Mode {mode!r} is neither ODL nor Online.")
        barred = N.non_odl_degree(programme)
        if barred:
            return res(NOT_APPROVED, "NOT_OFFERED_VIA_ODL_ONLINE",
                       f"{barred} degrees are not in the UGC-DEB scheme; UGC regulations generally do not "
                       f"permit them through ODL or Online mode, so no university is listed for them.")
        if not code:
            return res(INVALID_INPUT, "UNKNOWN_DEGREE",
                       f"Could not recognise a degree in {programme!r} (e.g. 'MBA', 'Master of Arts (English)').")

        uni_key, cands = self.resolve_university(university)
        if uni_key is None:
            if cands:
                return res(UNIVERSITY_AMBIGUOUS, "CONFIRM_UNIVERSITY",
                           "No exact match for this university name; confirm one of the candidates and re-check "
                           "with its exact name.",
                           university_candidates=cands)
            return res(UNIVERSITY_NOT_FOUND, "NOT_IN_DEB_LIST",
                       f"No institution by this name has any UGC-DEB approved ODL/Online programme "
                       f"({self.first_year} to {self.last_year}).")

        uni_name = self.display[uni_key]
        kw = {"university": uni_name, "university_candidates": cands}

        if not (self.first_year <= q_year <= self.last_year):
            return res(OUT_OF_COVERAGE, "YEAR_OUTSIDE_DATA",
                       f"The list covers {self.first_year} to {self.last_year}; {q_year} must be checked "
                       f"against older DEB approval notices.", **kw)

        deg = [r for r in self.by_uni[uni_key] if r["degree_code"] == code]
        if not deg:
            return res(NOT_APPROVED, "PROGRAMME_NEVER_APPROVED",
                       f"{uni_name} has no approved {code} programme in any year of the list.", **kw)

        generic_q = N.spec_is_generic(q_spec)
        spec = deg if generic_q else [r for r in deg if N.spec_matches(q_spec, r["specialisation"])]
        generic_recs = [r for r in deg if N.spec_is_generic(r["specialisation"])]

        def at(recs, mode_ok=True):
            return [r for r in recs if r["academic_year"] == q_year
                    and (q_mode is None or not mode_ok or r["mode_key"] == q_mode)]

        kw["approval_history"] = _history(spec or generic_recs)

        exact = at(spec)
        if exact:
            return res(APPROVED, "MATCH",
                       f"{uni_name} was approved to offer this programme in {q_year}"
                       + (f" in {q_mode} mode." if q_mode else "."),
                       matched_records=_public(exact), **kw)

        if not generic_q and at(generic_recs):
            return res(NEEDS_REVIEW, "BASE_DEGREE_ONLY",
                       f"{code} is approved for {q_year} without listed specialisations, so "
                       f"'{q_spec}' cannot be confirmed from this list alone.",
                       matched_records=_public(at(generic_recs)), **kw)

        other_mode = at(spec, mode_ok=False) or (not generic_q and at(generic_recs, mode_ok=False))
        if other_mode:
            modes = sorted({r["mode_key"] for r in other_mode})
            return res(NOT_APPROVED, "WRONG_MODE",
                       f"Approved in {q_year} only in {', '.join(modes)} mode, not {q_mode}.",
                       matched_records=_public(other_mode), **kw)

        if not any(r["academic_year"] == q_year for r in self.by_uni[uni_key]):
            # The list has gaps: many universities are missing for whole years.
            # Absence of the institution is not evidence that the programme was unapproved.
            listed_years = sorted({r["academic_year"] for r in self.by_uni[uni_key]})
            return res(NEEDS_REVIEW, "UNIVERSITY_NOT_LISTED_FOR_YEAR",
                       f"{uni_name} has no entries at all for {q_year} (listed for {', '.join(listed_years)}). "
                       f"Confirm with the university's DEB approval letter for that year.", **kw)

        if spec:
            return res(NOT_APPROVED, "YEAR_NOT_APPROVED",
                       f"Programme approved in other years ({', '.join(sorted(kw['approval_history']))}) "
                       f"but not for {q_year}.", **kw)

        listed = sorted({r["program_name"] for r in at(deg)}) or sorted({r["program_name"] for r in deg})
        return res(NOT_APPROVED, "SPECIALISATION_NOT_APPROVED",
                   f"{uni_name} offers {code} but '{q_spec}' is not among its approved specialisations.",
                   matched_records=[{"program_name": p} for p in listed[:25]], **kw)


def _history(recs: list[dict]) -> dict:
    h = defaultdict(set)
    for r in recs:
        h[r["academic_year"]].add(r["mode_key"])
    return {y: sorted(m for m in ms if m) for y, ms in sorted(h.items())}


def _public(recs: list[dict]) -> list[dict]:
    keep = ["year", "session", "mode", "name", "type", "state", "program_name", "level"]
    return [{k: r[k] for k in keep} for r in recs]
