"""Parsing tests.

Every bug found while collecting real records is pinned here, so the parser
keeps working on the layouts that actually appear on these sites.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import save_clips as s

STANDARD = """APU University Malaysia
Bachelor in Banking and Finance (Hons) with a specialism in Investment Analytics

Duration: 3 year(s)
English requirement: IELTS 6.0

Intake: Jul / Sep / Nov

Course fee for international students

Yearly Tuition fees

1st year: RM 34,900
2nd year: RM 36,100
3rd year: RM 37,500


Other fees

Library & Personal Bond Deposit (Refundable) : RM 1,500
University Administrative Fees : RM 7,000
Visa and Insurance : RM 3,600

University fees for this course exclude 6% tax (SST)
"""

EXTRA_BLANK_LINES = STANDARD.replace("\n\n", "\n\n\n\n").replace("\n\n\n\nOther", "\n\n\n\n\n\nOther")

SEMESTER_WITH_TOTAL = """Sunway University
Master in Finance

Intake: January / May / September

Course fee for international students

Semester 1: RM 20,000
Semester 2: RM 20,000
Total: RM 40,000
"""

COLON_IN_COURSE = """Taylor's University Malaysia
Bachelor in Banking and Finance: Investment Analytics

Duration: 3 years
English Requirement: IELTS 6.5

Intake: Jan / Aug

Tuition Fees

1st year: RM 40,000
2nd year: RM 42,000

Other fees
Registration fee: RM 2,000
Cautionary deposit (refundable): RM 1,000
"""

FLAT_FEE = """HELP University
Master of Data Science

Duration: 1.5 years
English requirement: TOEFL 90

Intake: Feb

Course fee: RM 33,500
"""

RESOURCE_IN_NAME = """APU University Malaysia
Bachelor of Arts (Honours) in Human Resource Management with a specialism in People Analytics

Duration: 3 year(s)
English requirement: IELTS Band 5.5

Intake: Sep / Nov

Yearly Tuition fees

1st year: RM 34,900
2nd year: RM 36,100
3rd year: RM 37,500
"""

MIXED_PERIODS = """HELP University
Master of Business Administration

Duration: 1 year
English requirement: IELTS 6.0

Intake: Jan

Tuition fees

Semester 1: RM 25,000
Semester 2: RM 25,000

1st year: RM 50,000
"""

JUNK = """Some university page
just random copied text
with no labels at all
"""

PER_SEMESTER_FEE = """UTP University Malaysia
MBA in Energy Management

Duration: 1 year
English requirement: IELTS 6.0

Intake: Jan / May

Course fee for international students

1st year: RM 41,900
Semester Fee: RM 400

Assessment Fee (Per Subject): RM 50
"""

PER_SEMESTER_FEE_NO_YEARS = """Cyberjaya University Malaysia (UoC)
Master in Business Administration (MBA)

Duration: 1.5 years
English requirement: IELTS 6.0

Intake: Jan

Semester Fee: RM 400
Semester 1: RM 20,000
Semester 2: RM 20,000
"""


def parsed(text):
    rec, problems = s.parse(text)
    assert not problems, problems
    return rec


def test_standard_record():
    rec = parsed(STANDARD)
    assert rec["university"] == "APU University Malaysia"
    assert rec["course"] == ("Bachelor in Banking and Finance (Hons) with a "
                             "specialism in Investment Analytics")
    assert rec["duration"] == "3 year(s)"
    assert rec["english_requirement"] == "IELTS 6.0"
    assert rec["intake"] == "Jul / Sep / Nov"
    assert rec["tuition_total_rm"] == "108500.00"
    assert "1st year: RM 34,900" in rec["tuition"]
    assert "Library & Personal Bond Deposit (Refundable): RM 1,500" in rec["other_fees"]
    assert "Visa and Insurance: RM 3,600" in rec["other_fees"]


def test_blank_line_spacing_is_irrelevant():
    loose = EXTRA_BLANK_LINES
    assert "\n\n\n" in loose
    assert parsed(loose) == parsed(STANDARD)


def test_semester_fees_and_total_line():
    rec = parsed(SEMESTER_WITH_TOTAL)
    assert rec["tuition"] == "Semester 1: RM 20,000 | Semester 2: RM 20,000"
    assert rec["tuition_total_rm"] == "40000.00"


def test_course_name_containing_a_colon():
    rec = parsed(COLON_IN_COURSE)
    assert rec["university"] == "Taylor's University Malaysia"
    assert rec["course"] == "Bachelor in Banking and Finance: Investment Analytics"
    assert rec["duration"] == "3 years"
    assert rec["english_requirement"] == "IELTS 6.5"
    assert rec["tuition_total_rm"] == "82000.00"
    assert "Registration fee: RM 2,000" in rec["other_fees"]


def test_single_flat_fee():
    rec = parsed(FLAT_FEE)
    assert rec["course"] == "Master of Data Science"
    assert rec["tuition_total_rm"] == "33500.00"
    assert rec["other_fees"] == ""


def test_resource_is_not_mistaken_for_a_header():
    assert parsed(RESOURCE_IN_NAME)["course"] == (
        "Bachelor of Arts (Honours) in Human Resource Management "
        "with a specialism in People Analytics")


def test_year_fees_win_over_semester_fees():
    rec = parsed(MIXED_PERIODS)
    assert rec["tuition"] == "1st year: RM 50,000"
    assert rec["tuition_total_rm"] == "50000.00"


def test_junk_is_rejected():
    rec, problems = s.parse(JUNK)
    assert problems
    assert rec["university"] == "Some university page"


def test_records_with_no_course_line_are_rejected():
    _, problems = s.parse("Some University\n\nDuration: 3 year(s)\nIntake: Sep\n")
    assert any("course" in p for p in problems)


def test_dedup_key_ignores_whitespace_and_case():
    assert s.dedup_key(STANDARD) == s.dedup_key(EXTRA_BLANK_LINES)
    assert s.dedup_key(STANDARD) == s.dedup_key("  " + STANDARD.replace("RM", "rm") + " \n\n")
    assert s.dedup_key(STANDARD) != s.dedup_key(FLAT_FEE)


def test_per_semester_fee_becomes_an_other_fee_not_lost():
    rec = parsed(PER_SEMESTER_FEE)
    assert rec["tuition"] == "1st year: RM 41,900"
    assert rec["tuition_total_rm"] == "41900.00"
    assert "Semester Fee: RM 400" in rec["other_fees"]
    assert "Assessment Fee (Per Subject): RM 50" in rec["other_fees"]


def test_per_semester_fee_kept_when_there_are_no_year_fees():
    rec = parsed(PER_SEMESTER_FEE_NO_YEARS)
    assert rec["tuition"] == "Semester 1: RM 20,000 | Semester 2: RM 20,000"
    assert rec["tuition_total_rm"] == "40000.00"
    assert "Semester Fee: RM 400" in rec["other_fees"]


def test_every_record_maps_to_the_full_row_width():
    for sample in (STANDARD, SEMESTER_WITH_TOTAL, COLON_IN_COURSE, FLAT_FEE,
                   RESOURCE_IN_NAME, MIXED_PERIODS):
        rec = parsed(sample)
        assert list(rec.keys()) == s.COLUMNS


def test_amount_parsing():
    assert s.amount("RM 34,900") == 34900
    assert s.amount("RM 1,500.50") == 1500.5
    assert s.amount("MYR 20,000") == 20000
    assert s.amount("on application") is None
    assert s.amount("42,000") == 42000