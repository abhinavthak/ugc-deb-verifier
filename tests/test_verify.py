import tempfile
import unittest
from pathlib import Path

from ugc_deb import normalize as N
from ugc_deb.scrape import build_db, parse
from ugc_deb.verify import Verifier

HEAD = ("<tr><th>Sr No</th><th>Year</th><th>Session</th><th>Mode</th><th>Name</th>"
        "<th>Type</th><th>State</th><th>Program name</th><th>UG/PG</th></tr>")

ROWS = [
    # year, mode, name, state, programme
    ("2026-27", "Online(OL)", "Guru Ghasidas Vishwavidyalaya", "Chhattisgarh", "MASTER OF ARTS (ENGLISH LITERATURE)"),
    ("2026-27", "Online(OL)", "Guru Ghasidas Vishwavidyalaya", "Chhattisgarh", "MASTER OF ARTS (HINDI)"),
    ("2025-26", "Online(OL)", "Guru Ghasidas Vishwavidyalaya", "Chhattisgarh", "MASTER OF ARTS (ENGLISH LITERATURE)"),
    ("2024-25", "Online(OL)", "Guru Ghasidas Vishwavidyalaya", "Chhattisgarh", "BACHELOR OF COMMERCE"),
    ("2023-24", "Online (Entitled)", "LOVELY PROFESSIONA L UNIVERSITY", "Punjab", "MASTER OF BUSINESS ADMINISTRATION"),
    ("2023-24", "ODL (Recognised)", "Lovely Professional University", "Punjab",
     "MASTER OF BUSINESS ADMINSTRATION (HR/MARKETING/FINANCE)"),
    ("2023-24", "ODL (Recognised)", "Tamil Nadu Open University(TNOU)", "Tamil Nadu", "MA HISTORY"),
    ("2025-26", "Open and Distance Learning (ODL)", "Indira Gandhi National Open University", "Delhi",
     "Master of Business Administration(Marketing Management)"),
    ("2023-24", "ODL (Recognised)", "Indira Gandhi National Open University", "Delhi", "BACHELOR OF ARTS"),
    ("2026-27", "Open and Distance Learning (ODL)", "", "", "MASTER OF ARTS (ARABIC)"),
]


def fixture_html() -> str:
    trs = "".join(
        f"<tr><td>{i}</td><td>{y}</td><td></td><td>{m}</td><td>{n}</td><td>State</td>"
        f"<td>{s}</td><td>{p}</td><td>PG</td></tr>"
        for i, (y, m, n, s, p) in enumerate(ROWS, 1)
    )
    return f"<html><table><thead>{HEAD}</thead><tbody>{trs}</tbody></table></html>"


class VerifierTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        db = Path(cls.tmp.name) / "deb.sqlite"
        build_db(parse(fixture_html()), db)
        cls.v = Verifier(db)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def check(self, *args, **kw):
        return self.v.check(*args, **kw)

    def test_approved(self):
        r = self.check("Guru Ghasidas Vishwavidyalaya", "MA English", "online", "2026")
        self.assertEqual((r.verdict, r.reason), ("APPROVED", "MATCH"))
        self.assertEqual(r.matched_records[0]["program_name"], "MASTER OF ARTS (ENGLISH LITERATURE)")

    def test_wrong_mode(self):
        r = self.check("Guru Ghasidas Vishwavidyalaya", "MA English", "ODL", "2026-27")
        self.assertEqual((r.verdict, r.reason), ("NOT_APPROVED", "WRONG_MODE"))

    def test_year_not_approved(self):
        r = self.check("Guru Ghasidas Vishwavidyalaya", "Master of Arts (English Literature)", "online", "2024")
        self.assertEqual((r.verdict, r.reason), ("NOT_APPROVED", "YEAR_NOT_APPROVED"))
        self.assertEqual(r.approval_history, {"2025-26": ["ONLINE"], "2026-27": ["ONLINE"]})

    def test_specialisation_not_approved(self):
        r = self.check("Guru Ghasidas Vishwavidyalaya", "MA", "online", "2026", specialisation="Astrophysics")
        self.assertEqual((r.verdict, r.reason), ("NOT_APPROVED", "SPECIALISATION_NOT_APPROVED"))

    def test_programme_never_approved(self):
        r = self.check("Guru Ghasidas Vishwavidyalaya", "MCA", "online", "2026")
        self.assertEqual(r.reason, "PROGRAMME_NEVER_APPROVED")

    def test_specialisation_inside_multi_list_with_typo_in_degree(self):
        r = self.check("Lovely Professional University", "MBA (Finance)", "ODL", "2023")
        self.assertEqual(r.verdict, "APPROVED")

    def test_base_degree_only_needs_review(self):
        r = self.check("LPU", "MBA (Finance)", "online", "2023")
        self.assertEqual((r.verdict, r.reason), ("NEEDS_REVIEW", "BASE_DEGREE_ONLY"))

    def test_university_missing_for_whole_year_is_review_not_rejection(self):
        r = self.check("IGNOU", "MBA", "ODL", "2024")
        self.assertEqual((r.verdict, r.reason), ("NEEDS_REVIEW", "UNIVERSITY_NOT_LISTED_FOR_YEAR"))

    def test_university_listed_that_year_but_programme_absent_is_rejection(self):
        r = self.check("IGNOU", "MBA", "ODL", "2023")
        self.assertEqual((r.verdict, r.reason), ("NOT_APPROVED", "YEAR_NOT_APPROVED"))

    def test_mode_optional(self):
        r = self.check("TNOU", "MA History", None, "2023-24")
        self.assertEqual(r.verdict, "APPROVED")

    def test_university_not_found(self):
        r = self.check("Sunrise University", "MBA", "online", "2023")
        self.assertEqual(r.verdict, "UNIVERSITY_NOT_FOUND")

    def test_blank_name_rows_never_match(self):
        r = self.check("Unknown Institute", "MA Arabic", "ODL", "2026")
        self.assertEqual(r.verdict, "UNIVERSITY_NOT_FOUND")

    def test_out_of_coverage(self):
        r = self.check("IGNOU", "MBA", "ODL", "2018")
        self.assertEqual(r.verdict, "OUT_OF_COVERAGE")

    def test_professional_degree(self):
        for prog in ["B.Tech", "LLB", "B.Sc Nursing", "MBBS", "B.Pharm"]:
            r = self.check("IGNOU", prog, "online", "2025")
            self.assertEqual(r.reason, "NOT_OFFERED_VIA_ODL_ONLINE", prog)

    def test_bad_inputs(self):
        self.assertEqual(self.check("IGNOU", "MBA", "online", "last year").reason, "BAD_YEAR")
        self.assertEqual(self.check("IGNOU", "MBA", "hybrid", "2025").reason, "BAD_MODE")
        self.assertEqual(self.check("IGNOU", "Diploma in Yoga", "online", "2025").reason, "UNKNOWN_DEGREE")


class NormalizeTest(unittest.TestCase):
    def test_programme_split(self):
        cases = {
            "MASTER OF BUSINESS ADMINISTRATION (FINANCE) - 2 years duration": ("MBA", "finance"),
            "MASTER OF BUSINESS ADMINSTRATION": ("MBA", ""),
            "BACHEOR OF COMMERCE": ("BCOM", ""),
            "MA PUBLIC ADMINISTRATION": ("MA", "public administration"),
            "M.Sc. Physics": ("MSC", "physics"),
            "BACHELOR OF BUSINESS ADMINISTRATIONTRAVEL AND TOURISM": ("BBA", "travel and tourism"),
            "BACHELOR OF ARTS (HONS) (GEOGRAPHY) - 4 YEARS": ("BA", "geography"),
        }
        for raw, (code, spec) in cases.items():
            got = N.split_programme(raw)
            self.assertEqual(got[:2], (code, spec), raw)

    def test_university_key_ignores_broken_words_and_deemed(self):
        self.assertEqual(N.university_key("KONERU LAKSHMAIAH EDUCATION FOUNDATI ON"),
                         N.university_key("Koneru Lakshmaiah Education Foundation"))
        self.assertEqual(N.university_key("JAIN (DEEMED-TO - BE UNIVERSITY)"), N.university_key("Jain"))

    def test_year_and_mode(self):
        self.assertEqual(N.academic_year("2023"), "2023-24")
        self.assertEqual(N.academic_year("2023-2024"), "2023-24")
        self.assertEqual(N.academic_year(2019), "2019-20")
        self.assertEqual(N.mode_key("Online (Entitled)"), "ONLINE")
        self.assertEqual(N.mode_key("ODL (Category-I)"), "ODL")
        self.assertEqual(N.mode_key("distance"), "ODL")

    def test_spec_matching(self):
        self.assertTrue(N.spec_matches("finance", "hr/marketing/finance"))
        self.assertTrue(N.spec_matches("human resource", "human resourse management"))
        self.assertFalse(N.spec_matches("finance", "marketing management"))


if __name__ == "__main__":
    unittest.main()
