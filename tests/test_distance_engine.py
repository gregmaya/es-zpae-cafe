from distance_engine import evaluate_candidate
from zones import ClassificationRule


def test_evaluate_candidate_prohibited_outright():
    zone_rules = {"alta": ClassificationRule(prohibited_outright=True)}
    result = evaluate_candidate("alta", zone_rules, strict_distances={}, lenient_distances={})
    assert result.prohibited_outright is True
    assert result.strict_pass is False
    assert result.lenient_pass is False


def test_evaluate_candidate_classification_not_in_rules_is_unregulated():
    # e.g. sin_superacion in most zones -- not mentioned in the rules
    # dict at all, meaning no ZPAE distance rule applies to it
    zone_rules = {"alta": ClassificationRule(prohibited_outright=True)}
    result = evaluate_candidate("sin_superacion", zone_rules, strict_distances={}, lenient_distances={})
    assert result.strict_pass is True
    assert result.lenient_pass is True
    assert result.prohibited_outright is False


def test_evaluate_candidate_passes_when_all_competitors_far():
    zone_rules = {
        "moderada": ClassificationRule(min_distance_m={"alta": 100, "moderada": 75, "baja": 50}),
    }
    result = evaluate_candidate(
        "moderada", zone_rules,
        strict_distances={"alta": 150, "moderada": 90, "baja": 60},
        lenient_distances={"alta": 150, "moderada": 90, "baja": 60},
    )
    # margins: alta 150-100=50, moderada 90-75=15, baja 60-50=10 -> baja binds
    assert result.strict_pass is True
    assert result.strict_margin_m == 10
    assert result.strict_binding_classification == "baja"


def test_evaluate_candidate_fails_when_a_competitor_too_close():
    zone_rules = {
        "moderada": ClassificationRule(min_distance_m={"alta": 100, "moderada": 75, "baja": 50}),
    }
    result = evaluate_candidate(
        "moderada", zone_rules,
        strict_distances={"alta": 150, "moderada": 60, "baja": 60},  # moderada margin = -15
        lenient_distances={"alta": 150, "moderada": 90, "baja": 60},
    )
    assert result.strict_pass is False
    assert result.strict_margin_m == -15
    assert result.strict_binding_classification == "moderada"
    assert result.lenient_pass is True
    assert result.interpretations_disagree is True


def test_evaluate_candidate_no_competitor_found_within_search_range():
    zone_rules = {
        "baja": ClassificationRule(min_distance_m={"alta": 150, "moderada": 75, "baja": 50}),
    }
    result = evaluate_candidate("baja", zone_rules, strict_distances={}, lenient_distances={})
    assert result.strict_pass is True
    assert result.strict_margin_m is None
    assert result.lenient_pass is True
