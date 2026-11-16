"""Independent Dijkstra/A*, user-hard-constraint routing, and loopless Yen alternatives.

All costs are nonnegative and at least edge.distance_m. The A* great-circle
heuristic is scaled by the network's minimum edge-distance/geodesic ratio,
clamped to 1, so it is admissible even if subsequently imported edges have
incorrectly short lengths. Distances are never derived from fabricated maps.
"""
from __future__ import annotations

import heapq
import itertools
import math
from dataclasses import dataclass
from time import perf_counter

from .graph import Network, age_days
from .demo_data import haversine

PROFILES = {
    "wheelchair": {"label": "Wheelchair", "max_slope": 8.0, "stairs": False, "high_curb": False},
    "walker": {"label": "Walker", "max_slope": 12.0, "stairs": False, "high_curb": False},
    "step_free": {"label": "Step-free", "max_slope": 14.0, "stairs": False, "high_curb": False},
    "pedestrian": {"label": "Pedestrian", "max_slope": None, "stairs": True, "high_curb": True},
}


@dataclass(frozen=True)
class Path:
    nodes: tuple[str, ...]
    edges: tuple[str, ...]
    cost: float


def active_barriers(edge: dict, profile: str) -> list[str]:
    """Confirmed hard constraints only; missing attributes remain unknown, not safe."""
    spec = PROFILES[profile]
    found = []
    if not spec["stairs"] and edge["stairs"] is not None and edge["stairs"] > 0:
        found.append(f"confirmed staircase ({edge['stairs']} steps)")
    if not spec["high_curb"] and edge["curb"] == "high":
        found.append("confirmed high curb")
    if spec["max_slope"] is not None and edge["slope_pct"] is not None and edge["slope_pct"] > spec["max_slope"]:
        found.append(f"confirmed {edge['slope_pct']:g}% slope")
    for report in edge["reports"]:
        if report["status"] != "verified":
            continue
        kind = report["obstacle_type"]
        if kind in ("blocked", "temporary_obstruction"):
            found.append("verified obstruction")
        elif kind == "stairs" and not spec["stairs"]:
            found.append("verified staircase report")
        elif kind == "missing_curb" and not spec["high_curb"]:
            found.append("verified inaccessible curb")
        elif kind == "steep_slope" and spec["max_slope"] is not None:
            found.append("verified steep-slope report")
        elif kind == "broken_surface" and profile in ("wheelchair", "walker") and report["severity"] >= 3:
            found.append("verified severe surface damage")
    return list(dict.fromkeys(found))


def edge_reliability(edge: dict) -> tuple[float, list[str]]:
    """Heuristic evidence confidence, not field-validated navigation probability."""
    missing = [key for key in ("stairs", "slope_pct", "surface", "curb") if edge[key] is None]
    age = age_days(edge["surveyed_at"])
    verified = {"verified": 0.99, "community": 0.75, "unverified": 0.48}[edge["verification"]]
    freshness = 0.35 if age is None else max(0.35, math.exp(-age / 180))
    completeness = (4 - len(missing)) / 4
    pending = sum(1 for report in edge["reports"] if report["status"] in ("pending", "reviewed"))
    # Boost when recent, independent verified reports corroborate observations.
    corroboration = 0.025 if any(report["status"] == "verified" for report in edge["reports"]) else 0
    probability = 0.55 + 0.18 * verified + 0.16 * completeness + 0.10 * freshness + corroboration
    probability -= min(0.22, 0.11 * pending)
    probability = max(0.30, min(0.985, probability))
    warnings = []
    if missing:
        warnings.append("unknown " + ", ".join(missing))
    if edge["verification"] != "verified":
        warnings.append(f"{edge['verification']} accessibility data")
    if age is None or age > 90:
        warnings.append("old or undated observation")
    if edge["crossing"] and edge["verification"] != "verified":
        warnings.append("unverified crossing")
    if pending:
        warnings.append(f"{pending} unverified community report(s)")
    if edge["surface"] in ("gravel", "rough"):
        warnings.append(f"{edge['surface']} surface")
    if edge["stairs"] and edge["stairs"] > 0:
        warnings.append(f"{edge['stairs']} confirmed steps")
    if edge["curb"] == "high":
        warnings.append("confirmed raised curb")
    if edge["slope_pct"] is not None and edge["slope_pct"] > 8:
        warnings.append(f"steep {edge['slope_pct']:g}% grade")
    for report in edge["reports"]:
        if report["status"] == "verified":
            warnings.append(f"verified {report['obstacle_type'].replace('_', ' ')} report")
    return probability, warnings


def edge_cost(edge: dict, profile: str, risk_aversion: int, mode: str = "accessible") -> float:
    if mode == "shortest":
        return edge["distance_m"]
    if active_barriers(edge, profile):
        return math.inf
    p, _ = edge_reliability(edge)
    risk = risk_aversion / 100
    cost_factor = 1.0 + (1 - p) * 2.1 * risk
    slope = edge["slope_pct"]
    if slope is None:
        cost_factor += 0.20 * risk
    elif profile != "pedestrian":
        cost_factor += max(0, slope - 3) * (0.04 if profile == "wheelchair" else 0.02)
    surface_penalties = {"smooth": 0, "paved": 0.02, "gravel": 0.30, "rough": 0.65, None: 0.18}
    factor = 1.0 if profile == "pedestrian" else 1.35
    cost_factor += surface_penalties[edge["surface"]] * factor
    if edge["curb"] is None:
        cost_factor += 0.15 * risk
    if edge["crossing"] and edge["verification"] == "unverified":
        cost_factor += 0.22 * risk
    return edge["distance_m"] * cost_factor


def _heuristic_scale(network: Network) -> float:
    ratios = [e["distance_m"] / e["straight_line_m"] for e in network.edges.values()
              if e["straight_line_m"] > 0]
    return max(0, min(1.0, min(ratios, default=0.0)))


def shortest_path(network: Network, start: str, end: str, profile: str = "wheelchair",
                  risk_aversion: int = 70, mode: str = "accessible", algorithm: str = "astar",
                  banned_edges: frozenset[str] = frozenset(),
                  banned_nodes: frozenset[str] = frozenset()) -> Path | None:
    if start not in network.nodes or end not in network.nodes or start in banned_nodes or end in banned_nodes:
        return None
    if start == end:
        return Path((start,), (), 0)
    if algorithm not in ("dijkstra", "astar"):
        raise ValueError("Only Dijkstra and A* are supported")
    goal = network.nodes[end]
    scale = _heuristic_scale(network) if algorithm == "astar" else 0

    def heuristic(node_id: str) -> float:
        item = network.nodes[node_id]
        return scale * haversine((item["lat"], item["lon"]), (goal["lat"], goal["lon"]))

    counter = itertools.count()
    frontier = [(heuristic(start), 0.0, next(counter), start)]
    dist = {start: 0.0}
    prev = {}
    while frontier:
        _, accumulated, _, node = heapq.heappop(frontier)
        if accumulated > dist.get(node, math.inf) + 1e-9:
            continue
        if node == end:
            break
        for neighbor, edge_id in network.adjacency.get(node, []):
            if edge_id in banned_edges or neighbor in banned_nodes:
                continue
            weight = edge_cost(network.edges[edge_id], profile, risk_aversion, mode)
            if math.isinf(weight):
                continue
            trial = accumulated + weight
            if trial < dist.get(neighbor, math.inf) - 1e-9:
                dist[neighbor] = trial
                prev[neighbor] = (node, edge_id)
                heapq.heappush(frontier, (trial + heuristic(neighbor), trial, next(counter), neighbor))
    if end not in dist:
        return None
    nodes = [end]
    edges = []
    cur = end
    while cur != start:
        parent, edge_id = prev[cur]
        nodes.append(parent)
        edges.append(edge_id)
        cur = parent
    return Path(tuple(reversed(nodes)), tuple(reversed(edges)), dist[end])


def alternatives(network: Network, start: str, end: str, profile: str,
                 risk_aversion: int, amount: int = 3, algorithm: str = "astar") -> list[Path]:
    """Yen's K-shortest simple paths, using the selected exact shortest-path solver."""
    first = shortest_path(network, start, end, profile, risk_aversion, algorithm=algorithm)
    if first is None:
        return []
    accepted = [first]
    candidates = []
    candidate_keys = set()
    counter = itertools.count()
    for _ in range(1, amount):
        previous = accepted[-1]
        for index in range(len(previous.nodes) - 1):
            root_nodes = previous.nodes[:index + 1]
            root_edges = previous.edges[:index]
            blocked = frozenset(path.edges[index] for path in accepted
                                if len(path.edges) > index and path.nodes[:index + 1] == root_nodes)
            spur = shortest_path(network, root_nodes[-1], end, profile, risk_aversion,
                                 algorithm=algorithm, banned_nodes=frozenset(root_nodes[:-1]),
                                 banned_edges=blocked)
            if spur is None:
                continue
            combined_nodes = root_nodes[:-1] + spur.nodes
            combined_edges = root_edges + spur.edges
            if combined_edges in candidate_keys or any(p.edges == combined_edges for p in accepted):
                continue
            cost = sum(edge_cost(network.edges[e], profile, risk_aversion) for e in combined_edges)
            candidate = Path(combined_nodes, combined_edges, cost)
            candidate_keys.add(combined_edges)
            heapq.heappush(candidates, (cost, next(counter), candidate))
        if not candidates:
            break
        _, _, candidate = heapq.heappop(candidates)
        accepted.append(candidate)
    return accepted


def path_detail(network: Network, path: Path, profile: str, kind: str) -> dict:
    segments = []
    total = sum(network.edges[e]["distance_m"] for e in path.edges)
    verified_m = 0.0
    confidence = 1.0
    barriers = []
    for edge_id in path.edges:
        e = network.edges[edge_id]
        p, warnings = edge_reliability(e)
        blockers = active_barriers(e, profile)
        confidence *= p
        if e["verification"] == "verified":
            verified_m += e["distance_m"]
        barriers.extend(blockers)
        days = age_days(e["surveyed_at"])
        segments.append({"edge_id": edge_id, "name": e["name"], "distance_m": e["distance_m"],
                         "confidence": round(p, 4), "verification": e["verification"],
                         "survey_age_days": round(days, 1) if days is not None else None,
                         "stairs": e["stairs"], "slope_pct": e["slope_pct"],
                         "surface": e["surface"], "curb": e["curb"],
                         "warnings": warnings, "hard_barriers": blockers,
                         "coordinates": e["coordinates"], "report_count": len(e["reports"])})
    return {
        "id": kind, "nodes": list(path.nodes), "edge_ids": list(path.edges),
        "distance_m": round(total, 1), "cost": round(path.cost, 2),
        "confidence": round(confidence, 4),
        "verified_coverage": round(verified_m / total, 4) if total else 1.0,
        "unsuitable_segments": sum(bool(s["hard_barriers"]) for s in segments),
        "barriers": list(dict.fromkeys(barriers)),
        "uncertain_segments": sum(
            s["verification"] != "verified" or s["survey_age_days"] is None
            or s["survey_age_days"] > 90 or any(s[k] is None for k in ("stairs", "slope_pct", "surface", "curb"))
            or any(r["status"] in ("pending", "reviewed") for r in network.edges[s["edge_id"]]["reports"])
            for s in segments),
        "segments": segments,
        "coordinates": [[network.nodes[n]["lon"], network.nodes[n]["lat"]] for n in path.nodes],
    }


def route_explanation(baseline: dict | None, chosen: dict | None) -> str:
    if not chosen:
        return "No feasible route meets the confirmed constraints for this profile. Unknown segments were not treated as verified safe."
    if not baseline:
        return "No connected pedestrian path was found between these points."
    if chosen["edge_ids"] == baseline["edge_ids"]:
        return "The shortest path also meets currently confirmed hard constraints. Inspect uncertain segments: this is not a safety guarantee."
    reasons = baseline["barriers"][:3]
    uncertain = [w for seg in baseline["segments"] for w in seg["warnings"] if "unverified crossing" in w]
    if uncertain:
        reasons.append("an unverified crossing")
    unique = list(dict.fromkeys(reasons))
    extra = chosen["distance_m"] - baseline["distance_m"]
    qualifier = "avoids " + ", ".join(unique) if unique else "reduces accessibility risk under your mobility profile"
    return f"Preferred route adds {max(0, extra):.0f} m over the absolute shortest path and {qualifier}. Unknown conditions remain possible."


def plan_route(network: Network, start: str, end: str, profile: str,
               algorithm: str = "astar", risk_aversion: int = 70, amount: int = 3) -> dict:
    began = perf_counter()
    baseline = shortest_path(network, start, end, profile, risk_aversion, "shortest", "dijkstra")
    options = alternatives(network, start, end, profile, risk_aversion, amount, algorithm)
    shortest = path_detail(network, baseline, profile, "shortest") if baseline else None
    routes = [path_detail(network, path, profile, f"route-{i + 1}") for i, path in enumerate(options)]
    for idx, route in enumerate(routes):
        route["label"] = "Preferred" if idx == 0 else f"Alternative {idx}"
    preferred = routes[0] if routes else None
    return {
        "shortest": shortest,
        "routes": routes,
        "explanation": route_explanation(shortest, preferred),
        "profile": profile, "algorithm": algorithm, "risk_aversion": risk_aversion,
        "network_revision": network.revision,
        "computation_ms": round((perf_counter() - began) * 1000, 3),
        "disclaimer": "Synthetic network. Confidence is heuristic, not a validated probability or a safe-route certification.",
    }
