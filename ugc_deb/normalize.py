"""Normalisation of the messy names found in the UGC-DEB programme list.

The source data has inconsistent case, stray spaces inside words
("FOUNDATI ON"), typos ("ADMINSTRATION"), and specialisations packed into
the programme name. Everything here turns a raw string into a comparable key.
"""
from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher


def ascii_fold(s: str) -> str:
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()


def squash(s: str) -> str:
    """Lowercase alphanumerics only. Immune to stray spaces and punctuation."""
    return re.sub(r"[^a-z0-9]", "", ascii_fold(s).lower())


def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio() if a and b else 0.0


# ---------------------------------------------------------------- universities

_UNI_NOISE = [
    "deemedtobeuniversity", "deemeduniversity", "deemedtobe",
]


def university_key(name: str) -> str:
    s = re.sub(r"\(.*?\)", " ", ascii_fold(name))  # "(Deemed to be University)", "(TNOU)", "(PUNE)"
    s = re.sub(r"\buniv\b\.?", "university", s, flags=re.I)
    s = squash(s)
    for noise in _UNI_NOISE:
        s = s.replace(noise, "")
    if s.startswith("the"):
        s = s[3:]
    return s


_UNI_GENERIC = ["university", "vishwavidyalaya", "vishwavidyalay", "vidyapeeth", "vidyapith"]


def university_core(key: str) -> str:
    """Distinctive part of a university_key, so 'Sunrise University' is not
    judged similar to 'Sri Sri University' just because both end in 'university'."""
    for w in _UNI_GENERIC:
        key = key.replace(w, "")
    return key


def university_acronyms(name: str) -> set[str]:
    """Acronyms given in parentheses in the source, e.g. 'Tamil Nadu Open University(TNOU)'."""
    out = set()
    for inner in re.findall(r"\(([^)]*)\)", name or ""):
        k = squash(inner)
        if 2 <= len(k) <= 8 and inner.strip().replace(".", "").isupper():
            out.add(k)
    return out


# ------------------------------------------------------------------- programmes

# Canonical degrees: code -> spellings (full names and abbreviations).
DEGREES: dict[str, list[str]] = {
    "MA": ["master of arts", "masters of arts", "ma"],
    "BA": ["bachelor of arts", "ba"],
    "MSC": ["master of science", "masters of science", "msc"],
    "BSC": ["bachelor of science", "bsc"],
    "MBA": ["master of business administration", "masters of business administration", "mba"],
    "BBA": ["bachelor of business administration", "bba"],
    "MCOM": ["master of commerce", "masters of commerce", "mcom"],
    "BCOM": ["bachelor of commerce", "bcom"],
    "MCA": ["master of computer applications", "master of computer application",
            "masters of computer applications", "mca"],
    "BCA": ["bachelor of computer applications", "bachelor of computer application", "bca"],
    "MED": ["master of education", "med"],
    "BED": ["bachelor of education", "bed"],
    "BEDSPL": ["bachelor of special education", "bachelor of education special education", "bedspl"],
    "MSW": ["master of social work", "msw"],
    "BSW": ["bachelor of social work", "bsw"],
    "MLIS": ["master of library and information science", "master of library and information sciences",
             "master of library information science", "master of library information sciences",
             "master of library science", "master of library sciences", "mlis", "mlisc", "mlib"],
    "BLIS": ["bachelor of library and information science", "bachelor of library and information sciences",
             "bachelor of library information science", "bachelor of library information sciences",
             "bachelor of library science", "bachelor of library sciences", "blis", "blisc", "blib"],
    "PGD": ["post graduate diploma", "postgraduate diploma", "post graduation diploma", "pg diploma", "pgd"],
    "BFA": ["bachelor of fine arts", "bfa"],
    "MFA": ["master of fine arts", "mfa"],
    "MJMC": ["master of journalism", "master of journalism and mass communication",
             "master of mass communication and journalism", "mjmc"],
    "BJMC": ["bachelor of journalism", "bachelor of journalism and mass communication", "bjmc"],
    "BMS": ["bachelor of management studies", "bms"],
    "MMS": ["master of management studies", "mms"],
    "BBM": ["bachelor of business management", "bbm"],
    "MTTM": ["master of tourism and travel management", "master of tourism travel management", "mttm"],
    "BTTM": ["bachelor of tourism and travel management", "bachelor of tourism travel management", "bttm"],
    "MPA": ["master of performing arts", "mpa"],
    "BPA": ["bachelor of performing arts", "bpa"],
    "ACHARYA": ["acharya"],
    "SHASTRI": ["shastri"],
}

_SPELLINGS = sorted(
    ((squash(sp), code) for code, sps in DEGREES.items() for sp in sps),
    key=lambda t: -len(t[0]),
)
_FULL_NAMES = [(k, c) for k, c in _SPELLINGS if len(k) > 8]
_ABBREV = {k: c for k, c in _SPELLINGS if len(k) <= 8}

# Professional degrees that never appear in the DEB list. UGC's ODL & Online
# regulations generally bar these from distance/online delivery.
NON_ODL_DEGREES: dict[str, list[str]] = {
    "B.Tech / B.E.": ["bachelor of technology", "bachelor of engineering", "btech", "be"],
    "M.Tech / M.E.": ["master of technology", "master of engineering", "mtech", "me"],
    "MBBS / medical": ["mbbs", "bachelor of medicine", "md", "ms surgery", "bds", "bachelor of dental surgery",
                       "bams", "bhms", "bums"],
    "Law": ["llb", "bachelor of laws", "bachelor of law", "llm", "master of laws", "ballb", "bballb"],
    "Pharmacy": ["bpharm", "bachelor of pharmacy", "mpharm", "master of pharmacy", "dpharm"],
    "Architecture": ["barch", "bachelor of architecture", "march", "master of architecture"],
    "Nursing": ["bscnursing", "bachelor of science in nursing", "msc nursing", "gnm", "anm"],
    "Physiotherapy": ["bpt", "bachelor of physiotherapy", "mpt", "master of physiotherapy"],
}
_NON_ODL = {squash(sp): label for label, sps in NON_ODL_DEGREES.items() for sp in sps}


def non_odl_degree(name: str) -> str | None:
    """Return a label if the programme is a professional degree outside the DEB scheme."""
    k = squash(re.sub(r"\(.*?\)", " ", ascii_fold(name)))
    if k in _NON_ODL:
        return _NON_ODL[k]
    if "nursing" in k:
        return "Nursing"
    first = squash((ascii_fold(name).split() or [""])[0])
    return _NON_ODL.get(first) if len(first) > 2 else None


_DURATION = re.compile(r"\(?\s*-?\s*0?\d\s*-?\s*years?(\s*duration)?\s*\)?", re.I)
_HONS = re.compile(r"\(?\s*hons?\.?\s*\)?", re.I)


def split_programme(name: str) -> tuple[str | None, str, bool]:
    """'MASTER OF BUSINESS ADMINISTRATION (FINANCE) - 2 years' -> ('MBA', 'finance', False).

    Returns (degree code or None, specialisation text, honours flag).
    """
    raw = ascii_fold(name or "").replace("–", "-")
    hons = bool(_HONS.search(raw))
    s = _DURATION.sub(" ", raw)
    s = _HONS.sub(" ", s)
    s = re.sub(r"\*\s*compl?ied.*$", "", s, flags=re.I)  # footnote "*Complied as B.A. with these subjects"
    s = s.replace("*", " ")

    # Head = text before the first "(", " - ", ":" or " in ". Rest = specialisation.
    m = re.search(r"\(|\s-\s|-\s|\s-|:|\bin\b", s, re.I)
    head, rest = (s[: m.start()], s[m.end():]) if m else (s, "")
    code = _match_degree(head)

    if code is None:
        # Separator may be missing ("BACHELOR OF BUSINESS ADMINISTRATIONTRAVEL AND TOURISM").
        hk = squash(s)
        for key, c in _FULL_NAMES:
            if hk.startswith(key):
                code, rest = c, s[_prefix_cut(s, key):]
                break

    if code is None:
        # Abbreviation followed by specialisation: "MA PUBLIC ADMINISTRATION", "M.Sc. Physics".
        words = s.split()
        for n in (2, 1):
            if len(words) > n:
                c = _ABBREV.get(squash(" ".join(words[:n])))
                if c:
                    code, rest = c, " ".join(words[n:])
                    break
    spec = _clean_spec(rest)
    return code, spec, hons


def _prefix_cut(s: str, squashed_prefix: str) -> int:
    n = 0
    for i, ch in enumerate(s):
        if re.match(r"[A-Za-z0-9]", ch):
            n += 1
            if n == len(squashed_prefix):
                return i + 1
    return len(s)


def _match_degree(head: str) -> str | None:
    hk = squash(head)
    if not hk:
        return None
    for key, code in _SPELLINGS:
        if hk == key:
            return code
    # Typos: "MASTER OF BUSINESS ADMINSTRATION", "BACHEOR OF COMMERCE".
    best, best_score = None, 0.0
    for key, code in _FULL_NAMES:
        sc = similarity(hk, key)
        if sc > best_score:
            best, best_score = code, sc
    return best if best_score >= 0.9 else None


_SPEC_STOP = {"and", "of", "in", "the", "with", "general", "core", "hons", "honours", "programme", "program",
              "combination", "subjects", "subject", "from", "ugc", "list", "any", "three", "two"}


def _clean_spec(s: str) -> str:
    s = re.sub(r"[()\[\]]", " ", s)
    s = s.replace("&", " and ")
    s = re.sub(r"[^A-Za-z0-9/,]+", " ", s).strip(" ,/-").lower()
    return " ".join(s.split())


def spec_tokens(spec: str) -> list[str]:
    return [t for t in re.split(r"[^a-z0-9]+", spec.lower())
            if t and not t.isdigit() and t not in _SPEC_STOP]


def spec_is_generic(spec: str) -> bool:
    return not spec_tokens(spec)


def spec_matches(query_spec: str, record_spec: str) -> bool:
    """True if every meaningful word of the query appears (allowing typos) in the record.

    A record often lists several specialisations ("HR/MM/FM", "FINANCE, MARKETING"),
    so containment, not equality, is the right test.
    """
    q = spec_tokens(query_spec)
    r = spec_tokens(record_spec)
    if not q:
        return True
    if not r:
        return False
    return all(any(t == u or (len(t) > 4 and similarity(t, u) >= 0.85) for u in r) for t in q)


# ------------------------------------------------------------------ mode / year

def mode_key(mode: str) -> str | None:
    m = squash(mode)
    if not m:
        return None
    if "online" in m or m in {"ol", "ole"}:
        return "ONLINE"
    if "odl" in m or "distance" in m or "correspondence" in m:
        return "ODL"
    return None


def academic_year(value) -> str | None:
    """'2023', 2023, '2023-24', '2023-2024', '2023/24' -> '2023-24'.

    A bare year is read as the July session start (Indian academic year).
    """
    s = str(value or "").strip()
    m = re.match(r"^(\d{4})\s*(?:[-/–]\s*(\d{2}|\d{4}))?$", s)
    if not m:
        return None
    start = int(m.group(1))
    return f"{start}-{str(start + 1)[-2:]}"
