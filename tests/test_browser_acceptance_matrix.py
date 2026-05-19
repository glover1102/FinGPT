from __future__ import annotations

from scripts.browser_acceptance_matrix import build_acceptance_report


def test_browser_acceptance_matrix_keeps_iab_and_fallback_separate() -> None:
    report = build_acceptance_report(
        ui_contract={"status": "passed", "missing_markers": []},
        browser_use_status="blocked",
        browser_use_error="No Codex IAB backends were discovered",
        playwright_status="passed",
        fallback_screenshot="reports/quant_lab_ui.png",
    )

    assert report["browser_use_iab"]["status"] == "blocked"
    assert report["browser_use_iab"]["satisfies_explicit_browser_use"] is False
    assert report["playwright_fallback"]["status"] == "passed"
    assert report["summary"]["explicit_browser_use_satisfied"] is False
    assert report["summary"]["fallback_available"] is True
    assert report["summary"]["release_evidence_level"] == "playwright_fallback"
