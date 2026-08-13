"""
Tests — Module 5: Hiring Score Calculation & Display
Covers: matching engine helpers (normalize_skills, compare_skills,
        compare_experience, compare_education, compare_certifications,
        calculate_overall_score) and the analytics _hiring_score helper.
All pure-function tests — no DB required.
"""

import pytest
from matching_engine import (
    normalize_skills,
    compare_skills,
    compare_experience,
    compare_education,
    compare_certifications,
    calculate_overall_score,
)
from milestone4.recruitment_analytics import _hiring_score


# ── normalize_skills ───────────────────────────────────────────────────────

class TestNormalizeSkills:

    def test_basic_split(self):
        result = normalize_skills("Python, Django, MySQL")
        assert result == {"python", "django", "mysql"}

    def test_empty_string(self):
        assert normalize_skills("") == set()

    def test_none_input(self):
        assert normalize_skills(None) == set()

    def test_whitespace_trimmed(self):
        result = normalize_skills("  python  ,  django  ")
        assert "python" in result
        assert "django" in result

    def test_duplicates_removed(self):
        result = normalize_skills("python, python, Python")
        assert len(result) == 1

    def test_single_skill(self):
        assert normalize_skills("python") == {"python"}


# ── compare_skills ─────────────────────────────────────────────────────────

class TestCompareSkills:

    def test_perfect_match(self):
        r = compare_skills({"python", "django"}, {"python", "django"})
        assert r["match_percentage"] == 100.0
        assert r["missing_count"] == 0

    def test_partial_match(self):
        r = compare_skills({"python"}, {"python", "django"})
        assert r["match_percentage"] == 50.0
        assert "django" in r["missing_skills"]

    def test_no_match(self):
        r = compare_skills({"java"}, {"python", "django"})
        assert r["match_percentage"] == 0.0
        assert r["matched_count"] == 0

    def test_empty_jd_skills(self):
        """If JD has no skills, match percentage is 0 (no division by zero)."""
        r = compare_skills({"python"}, set())
        assert r["match_percentage"] == 0.0

    def test_empty_resume_skills(self):
        r = compare_skills(set(), {"python", "django"})
        assert r["match_percentage"] == 0.0
        assert r["missing_count"] == 2

    def test_additional_skills_counted(self):
        r = compare_skills({"python", "rust"}, {"python"})
        assert "rust" in r["additional_skills"]
        assert r["additional_count"] == 1

    def test_result_keys_present(self):
        r = compare_skills({"python"}, {"python"})
        for key in ("matched_skills", "missing_skills", "additional_skills",
                    "match_percentage", "matched_count", "missing_count", "additional_count"):
            assert key in r


# ── compare_experience ─────────────────────────────────────────────────────

class TestCompareExperience:

    def test_meets_mid_level(self):
        r = compare_experience("3 years at TechCorp", "Mid-Level")
        assert r["meets_experience"] is True

    def test_does_not_meet_senior(self):
        r = compare_experience("2 years experience", "Senior")
        assert r["meets_experience"] is False

    def test_fresher_always_meets(self):
        r = compare_experience("", "Fresher")
        assert r["meets_experience"] is True

    def test_no_years_in_text(self):
        r = compare_experience("Worked at various companies", "Mid-Level")
        assert r["candidate_years_found"] == 0

    def test_multiple_year_mentions(self):
        """Should take the max years found."""
        r = compare_experience("1 year intern, 4 years full-time", "Mid-Level")
        assert r["candidate_years_found"] == 4
        assert r["meets_experience"] is True

    def test_unknown_level_defaults_to_zero(self):
        r = compare_experience("0 years", "UnknownLevel")
        assert r["meets_experience"] is True   # 0 >= 0


# ── compare_education ──────────────────────────────────────────────────────

class TestCompareEducation:

    def test_matching_degree(self):
        r = compare_education("B.Tech in Computer Science", "B.Tech required")
        assert r["meets_education"] is True

    def test_no_jd_requirement_passes(self):
        r = compare_education("High School", "No specific requirement")
        assert r["meets_education"] is True

    def test_missing_required_degree(self):
        r = compare_education("High School diploma", "MBA required")
        assert r["meets_education"] is False

    def test_empty_candidate_education(self):
        r = compare_education("", "B.Tech required")
        assert r["meets_education"] is False

    def test_empty_jd_requirements(self):
        r = compare_education("B.Tech", "")
        assert r["meets_education"] is True


# ── compare_certifications ─────────────────────────────────────────────────

class TestCompareCertifications:

    def test_cert_matched(self):
        r = compare_certifications("AWS Certified Developer", "AWS Certified Developer")
        assert r["certification_matched"] is True

    def test_cert_not_matched(self):
        r = compare_certifications("Google Cloud Certified", "AWS Certified Developer")
        assert r["certification_matched"] is False

    def test_no_jd_cert_required(self):
        r = compare_certifications("anything", "")
        assert r["certification_matched"] is True

    def test_none_jd_cert(self):
        r = compare_certifications("anything", None)
        assert r["certification_matched"] is True

    def test_empty_candidate_cert_no_jd_req(self):
        r = compare_certifications("", "")
        assert r["certification_matched"] is True


# ── calculate_overall_score ────────────────────────────────────────────────

class TestCalculateOverallScore:

    def test_perfect_score(self):
        r = calculate_overall_score(100.0, True, True, True)
        assert r["overall_score"] == 100.0
        assert r["grade"] == "A"

    def test_zero_score(self):
        r = calculate_overall_score(0.0, False, False, False)
        assert r["overall_score"] == 0.0
        assert r["grade"] == "D"

    def test_weights_sum_correctly(self):
        # skills=60%, exp=20%, edu=15%, cert=5%
        r = calculate_overall_score(100.0, True, True, True)
        expected = 60.0 + 20.0 + 15.0 + 5.0
        assert r["overall_score"] == pytest.approx(expected)

    def test_grade_a_threshold(self):
        r = calculate_overall_score(100.0, True, True, True)
        assert r["grade"] == "A"

    def test_grade_b_threshold(self):
        # 60*0.6 + 0 + 0 + 0 = 36 → D; need ~60: 60*0.6=36, +20+15=71 → B
        r = calculate_overall_score(60.0, True, True, False)
        assert r["grade"] in ("A", "B")

    def test_verdict_highly_recommended(self):
        r = calculate_overall_score(100.0, True, True, True)
        assert "Highly Recommended" in r["verdict"]

    def test_verdict_not_recommended(self):
        r = calculate_overall_score(0.0, False, False, False)
        assert "Not Recommended" in r["verdict"]

    def test_result_keys_present(self):
        r = calculate_overall_score(50.0, True, False, False)
        for key in ("overall_score", "grade", "verdict"):
            assert key in r


# ── _hiring_score (analytics composite) ───────────────────────────────────

class TestHiringScore:

    def test_with_interview_score(self):
        # 60% resume + 40% interview
        score = _hiring_score(80.0, 60.0)
        assert score == pytest.approx(72.0)

    def test_without_interview_score(self):
        score = _hiring_score(75.0, None)
        assert score == pytest.approx(75.0)

    def test_zero_resume_zero_interview(self):
        assert _hiring_score(0.0, 0.0) == pytest.approx(0.0)

    def test_max_scores(self):
        assert _hiring_score(100.0, 100.0) == pytest.approx(100.0)

    def test_interview_score_as_string_float(self):
        """interview_score may come from DB as Decimal or string."""
        score = _hiring_score(80.0, "60.0")
        assert score == pytest.approx(72.0)
