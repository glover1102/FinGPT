from core.utils.confidence_calibration import apply_confidence_caps


def test_no_evidence_caps_confidence():
    rationale = apply_confidence_caps(0.90, evidence_count=0, numeric_grounding_rate=1.0, claim_support_rate=1.0)
    assert rationale.final_confidence <= 0.20
    assert rationale.caps_applied


def test_only_low_quality_evidence_caps_confidence():
    rationale = apply_confidence_caps(
        0.90,
        evidence_count=3,
        low_quality_only=True,
        numeric_grounding_rate=1.0,
        claim_support_rate=1.0,
    )
    assert rationale.final_confidence <= 0.55


def test_poor_numeric_grounding_caps_confidence():
    rationale = apply_confidence_caps(0.90, evidence_count=2, numeric_grounding_rate=0.40, claim_support_rate=1.0)
    assert rationale.final_confidence <= 0.60


def test_high_quality_evidence_allows_higher_confidence():
    rationale = apply_confidence_caps(
        0.86,
        evidence_count=5,
        numeric_grounding_rate=0.95,
        claim_support_rate=0.90,
        stale_context_rate=0.0,
        required_bucket_coverage=0.80,
        official_support=True,
        evidence_quality_average=0.85,
        freshness_coverage=0.90,
    )
    assert rationale.final_confidence == 0.86
    assert not rationale.caps_applied
    assert rationale.positive_factors
