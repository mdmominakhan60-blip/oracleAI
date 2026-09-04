import pytest

from scripts import domain_qa


def test_angular_delta_wraps_across_zero():
    assert domain_qa.angular_delta(359.99, 0.01) == pytest.approx(0.02)
    assert domain_qa.angular_delta(10.0, 10.0) == 0.0


def test_critical_astronomy_reference_cases_pass_with_explicit_limitations():
    results = [domain_qa.check_case(case) for case in domain_qa.CASES]
    assert len(results) == 8
    assert all(result["passed"] for result in results)
    exact = [result for result in results if result["comparison"] == "numeric_planets_houses_angles"]
    assert exact
    assert all(result["max_planet_delta_deg"] <= domain_qa.THRESHOLD_DEG for result in exact)
    assert all(result["max_house_delta_deg"] <= domain_qa.THRESHOLD_DEG for result in exact)
    assert all(result["max_angle_delta_deg"] <= domain_qa.THRESHOLD_DEG for result in exact)
    polar = next(result for result in results if result["id"] == "high_latitude")
    assert polar["unverified"] == ["houses", "ASC", "MC"]
    date_only = next(result for result in results if result["id"] == "unknown_time")
    assert date_only["precision"] == "date_only"
    assert date_only["house_count"] == 0
