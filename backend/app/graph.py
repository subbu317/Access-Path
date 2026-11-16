"""Build the bidirectional geospatial graph from stored edges and moderated reports."""
from __future__ import annotations

import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone

from .db import expire_reports, revision
from .demo_data import haversine


@dataclass
class Network:
    nodes: dict
    edges: dict
    adjacency: dict
    revision: int
    source: str = "Synthetic demonstration network; not actual geographic routes"


def age_days(value: str | None) -> float | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return max(0.0, (datetime.now(timezone.utc) - dt).total_seconds() / 86400)
    except ValueError:
        return None


def load_network(db: sqlite3.Connection) -> Network:
    expire_reports(db)
    nodes = {r["id"]: dict(r) for r in db.execute("SELECT * FROM nodes")}
    active = defaultdict(list)
    for r in db.execute("SELECT * FROM reports WHERE status IN ('pending','reviewed','verified') ORDER BY id"):
        active[r["edge_id"]].append(dict(r))
    edges = {}
    adjacency = defaultdict(list)
    for record in db.execute("SELECT * FROM edges"):
        edge = dict(record)
        edge["crossing"] = bool(edge["crossing"])
        edge["reports"] = active[edge["id"]]
        a, b = edge["source"], edge["target"]
        edge["coordinates"] = [
            [nodes[a]["lon"], nodes[a]["lat"]],
            [nodes[b]["lon"], nodes[b]["lat"]],
        ]
        # Mark geometry validity; user-supplied importers must not assume geodesic distance.
        edge["straight_line_m"] = haversine(
            (nodes[a]["lat"], nodes[a]["lon"]), (nodes[b]["lat"], nodes[b]["lon"])
        )
        edges[edge["id"]] = edge
        adjacency[a].append((b, edge["id"]))
        adjacency[b].append((a, edge["id"]))
    for items in adjacency.values():
        items.sort(key=lambda pair: (pair[0], pair[1]))
    return Network(nodes, edges, dict(adjacency), revision(db))


def network_payload(network: Network) -> dict:
    return {
        "nodes": list(network.nodes.values()),
        "edges": list(network.edges.values()),
        "network_revision": network.revision,
        "disclaimer": network.source,
    }


def geojson(network: Network) -> dict:
    features = []
    for e in network.edges.values():
        properties = {key: value for key, value in e.items() if key not in ("coordinates", "straight_line_m")}
        features.append({"type": "Feature", "id": e["id"],
                         "geometry": {"type": "LineString", "coordinates": e["coordinates"]},
                         "properties": properties})
    for node in network.nodes.values():
        features.append({"type": "Feature", "id": node["id"],
                         "geometry": {"type": "Point", "coordinates": [node["lon"], node["lat"]]},
                         "properties": {"id": node["id"], "label": node["label"], "kind": node["kind"]}})
    return {"type": "FeatureCollection", "name": "AccessPath synthetic demo",
            "network_revision": network.revision, "features": features}
