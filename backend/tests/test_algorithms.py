import math

import pytest

from app.routing import active_barriers, alternatives, edge_cost, edge_reliability, plan_route, shortest_path


def test_graph_is_connected_and_geometries_valid(graph):
    assert len(graph.nodes) == 20
    assert len(graph.edges) == 37
    assert all(edge["distance_m"] >= edge["straight_line_m"] - 0.15 for edge in graph.edges.values())
    assert all(len(e["coordinates"]) == 2 for e in graph.edges.values())


@pytest.mark.parametrize("profile", ["wheelchair", "walker", "step_free", "pedestrian"])
def test_dijkstra_and_astar_match_optimal_cost(graph, profile):
    for start in graph.nodes:
        for end in graph.nodes:
            if start == end:
                continue
            dij = shortest_path(graph, start, end, profile=profile, algorithm="dijkstra")
            astar = shortest_path(graph, start, end, profile=profile, algorithm="astar")
            assert (dij is None) == (astar is None)
            if dij:
                assert math.isclose(dij.cost, astar.cost, rel_tol=1e-9)
                assert all(math.isfinite(edge_cost(graph.edges[e], profile, 70)) for e in dij.edges)


def test_shortest_is_not_misrepresented_as_accessible(graph):
    baseline = shortest_path(graph, "N1", "N5", mode="shortest", algorithm="dijkstra")
    assert baseline is not None
    assert any("staircase" in s for e in baseline.edges for s in active_barriers(graph.edges[e], "wheelchair"))
    accessible = shortest_path(graph, "N1", "N5", profile="wheelchair", algorithm="astar")
    assert accessible
    assert all(not active_barriers(graph.edges[e], "wheelchair") for e in accessible.edges)
    assert accessible.edges != baseline.edges


def test_obstacle_profiles_and_unknown_do_not_equate_to_verified_safe(graph):
    stair = next(e for e in graph.edges.values() if e["name"] == "North staircase")
    assert active_barriers(stair, "wheelchair")
    assert not active_barriers(stair, "pedestrian")
    uncertain = next(e for e in graph.edges.values() if e["name"] == "Unverified north crossing")
    conf, warnings = edge_reliability(uncertain)
    assert conf < 0.99
    assert "unverified crossing" in warnings
    assert not active_barriers(uncertain, "wheelchair")  # unknown is not a proven barrier either


def test_heuristic_edge_cost_at_least_distance(graph):
    for edge in graph.edges.values():
        for profile in ("wheelchair", "walker", "step_free", "pedestrian"):
            cost = edge_cost(edge, profile, 95)
            assert math.isinf(cost) or cost >= edge["distance_m"]
    edge = next(e for e in graph.edges.values() if e["name"] == "Unverified north crossing")
    assert edge_cost(edge, "wheelchair", 100) > edge_cost(edge, "wheelchair", 0)


def test_yen_alternatives_are_unique_loopless_and_sorted(graph):
    paths = alternatives(graph, "N1", "N5", "wheelchair", risk_aversion=70, amount=5)
    assert len(paths) >= 3
    assert len({p.edges for p in paths}) == len(paths)
    assert all(len(p.nodes) == len(set(p.nodes)) for p in paths)
    assert all(paths[i].cost <= paths[i + 1].cost + 1e-8 for i in range(len(paths)-1))


def test_route_explanation_and_confidence(graph):
    result = plan_route(graph, "N1", "N5", "wheelchair")
    assert result["routes"]
    assert result["shortest"]["unsuitable_segments"] > 0
    assert result["routes"][0]["unsuitable_segments"] == 0
    assert "staircase" in result["explanation"]
    assert 0 < result["routes"][0]["confidence"] <= 1
    assert 0 <= result["routes"][0]["verified_coverage"] <= 1
