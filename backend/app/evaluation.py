"""Reproducible real computation benchmarks and *synthetic* confidence calibration."""
from __future__ import annotations

import random
from statistics import mean

from .graph import Network, age_days
from .routing import active_barriers, edge_reliability, plan_route

# Deliberately distinct synthetic truth model from edge_reliability(). This is
# an illustrative calibration experiment, NOT empirical field calibration.
PAIRS = [
    ("N1", "N5"), ("N1", "N10"), ("N6", "N15"), ("N16", "N20"),
    ("N2", "N19"), ("N3", "N12"), ("N4", "N18"), ("N7", "N15"),
    ("N11", "N20"), ("N5", "N16"), ("N6", "N14"), ("N10", "N17"),
]


def synthetic_true_probability(edge: dict, profile: str) -> float:
    if active_barriers(edge, profile):
        return 0.0
    value = {"verified": 0.985, "community": 0.89, "unverified": 0.78}[edge["verification"]]
    value -= 0.075 * sum(edge[k] is None for k in ("stairs", "slope_pct", "surface", "curb"))
    if (age_days(edge["surveyed_at"]) or 9999) > 90:
        value -= 0.075
    if any(r["status"] in ("pending", "reviewed") for r in edge["reports"]):
        value -= 0.12
    if edge["surface"] == "rough" and profile in ("wheelchair", "walker"):
        value -= 0.16
    return min(0.995, max(0.08, value))


def calculate_evaluation(network: Network, trials: int = 50, seed: int = 41) -> dict:
    """All figures derive from executed routing and deterministic simulated truth."""
    rng = random.Random(seed)
    cases = []
    predictions = []
    outcomes = []
    for profile in ("wheelchair", "walker", "step_free", "pedestrian"):
        for start, end in PAIRS:
            result = plan_route(network, start, end, profile, amount=1, risk_aversion=75)
            shortest = result["shortest"]
            route = result["routes"][0] if result["routes"] else None
            if not route or not shortest:
                cases.append({"profile": profile, "from": start, "to": end,
                              "feasible": False, "computation_ms": result["computation_ms"]})
                continue
            b_bad = shortest["unsuitable_segments"]
            a_bad = route["unsuitable_segments"]
            cases.append({
                "profile": profile, "from": start, "to": end, "feasible": True,
                "shortest_m": shortest["distance_m"], "selected_m": route["distance_m"],
                "distance_overhead_pct": round(100 * (route["distance_m"] / shortest["distance_m"] - 1), 2),
                "shortest_unsuitable": b_bad, "selected_unsuitable": a_bad,
                "confirmed_obstacles_avoided": max(0, b_bad - a_bad),
                "verified_coverage": route["verified_coverage"],
                "confidence": route["confidence"], "computation_ms": result["computation_ms"],
            })
            # Evaluate route-level predicted confidence against independent
            # Bernoulli draws for *each* edge in a synthetic hidden environment.
            truths = [synthetic_true_probability(network.edges[e], profile) for e in route["edge_ids"]]
            for _ in range(trials):
                actual_passed = int(all(rng.random() < probability for probability in truths))
                predictions.append(route["confidence"])
                outcomes.append(actual_passed)

    feasible = [case for case in cases if case["feasible"]]
    buckets = []
    ece = 0.0
    for i in range(5):
        sample = [(p, y) for p, y in zip(predictions, outcomes)
                  if i / 5 <= p < (i + 1) / 5 or (i == 4 and p == 1)]
        if not sample:
            continue
        predicted = mean(x[0] for x in sample)
        observed = mean(x[1] for x in sample)
        ece += len(sample) / len(predictions) * abs(predicted - observed)
        buckets.append({"range": f"{i * 20}–{(i + 1) * 20}%", "count": len(sample),
                        "predicted": round(predicted, 4), "observed": round(observed, 4)})
    return {
        "network_revision": network.revision,
        "methodology": "12 fixed OD pairs × 4 profiles; 50 synthetic outcomes per feasible route by default. No field data.",
        "case_count": len(cases), "feasible_cases": len(feasible),
        "mean_shortest_unsuitable": round(mean(c["shortest_unsuitable"] for c in feasible), 3) if feasible else None,
        "mean_accesspath_unsuitable": round(mean(c["selected_unsuitable"] for c in feasible), 3) if feasible else None,
        "mean_distance_overhead_pct": round(mean(c["distance_overhead_pct"] for c in feasible), 2) if feasible else None,
        "confirmed_obstacles_avoided": sum(c["confirmed_obstacles_avoided"] for c in feasible),
        "mean_verified_coverage": round(mean(c["verified_coverage"] for c in feasible), 4) if feasible else None,
        "mean_route_compute_ms": round(mean(c["computation_ms"] for c in cases), 3),
        "confidence_calibration": {
            "synthetic_outcomes": len(outcomes),
            "brier_score": round(mean((p - y) ** 2 for p, y in zip(predictions, outcomes)), 4) if outcomes else None,
            "expected_calibration_error": round(ece, 4),
            "bins": buckets,
            "disclaimer": "Synthetic edge outcomes from a separate hypothetical truth model. Not field-validated risk or safety probabilities.",
        },
        "cases": cases,
    }
