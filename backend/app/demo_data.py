"""Entirely synthetic pedestrian network. Coordinates are illustrative, not geographic truth."""
from __future__ import annotations

from datetime import timedelta
from math import asin, cos, radians, sin, sqrt

from .db import iso, utcnow

NODE_LABELS = [
    "Welcome Gate", "North Plaza", "Library Walk", "Market Passage", "Community Hub",
    "Garden Entry", "West Ramp", "Central Court", "East Ramp", "Transit Hall",
    "Garden South", "Water Square", "South Court", "East Garden", "Clinic",
    "Trail Start", "Lake Path", "South Bridge", "Arcade", "South Exit",
]


def haversine(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1 = map(radians, a)
    lat2, lon2 = map(radians, b)
    h = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371000 * asin(min(1, sqrt(h)))


def seed(db) -> None:
    now = utcnow()
    coords = {}
    for i, label in enumerate(NODE_LABELS):
        r, c = divmod(i, 5)
        node = f"N{i + 1}"
        # Coordinates deliberately lie over open water. No real-world paths are implied.
        lat = 0.0200 - r * 0.00052
        lon = 0.0200 + c * 0.00055
        coords[node] = (lat, lon)
        db.execute("INSERT INTO nodes(id,label,lat,lon,kind) VALUES(?,?,?,?,?)", (
            node, label, lat, lon,
            "destination" if i in (0, 4, 9, 14, 19) else "junction",
        ))

    pairs = []
    for r in range(4):
        for c in range(4):
            n = 1 + r * 5 + c
            pairs.append((n, n + 1))
    for r in range(3):
        for c in range(5):
            n = 1 + r * 5 + c
            pairs.append((n, n + 5))
    pairs += [(2, 8), (8, 14), (6, 12), (12, 18), (9, 15), (14, 20)]

    # Metadata overrides for synthetic accessibility demonstrations.
    configs = {
        (2, 3): dict(stairs=8, verification="verified", name="North staircase"),
        (3, 4): dict(slope_pct=None, curb=None, crossing=1, verification="unverified", name="Unverified north crossing"),
        (7, 8): dict(curb="high", verification="verified", name="Raised curb at central court"),
        (8, 9): dict(name="Central east promenade"),
        (2, 7): dict(slope_pct=10.0, verification="verified", name="Steep north slope"),
        (4, 9): dict(curb="high", name="Market drop curb"),
        (11, 12): dict(slope_pct=10.5, name="Steep southern gradient"),
        (13, 14): dict(surface="gravel", days_ago=100, name="Aged gravel promenade"),
        (17, 18): dict(crossing=1, verification="unverified", curb=None, name="Unassessed bridge crossing"),
        (14, 15): dict(stairs=4, name="Clinic short staircase"),
        (19, 20): dict(surface="rough", name="Rough east footpath"),
        (12, 13): dict(verification="community", name="Community-surveyed plaza"),
        (6, 7): dict(verification="verified", name="Level garden walkway"),
        (9, 10): dict(slope_pct=6.5, name="Transit incline"),
        (3, 8): dict(slope_pct=None, verification="unverified", name="Unknown library ramp"),
        (8, 14): dict(surface="gravel", verification="community", name="Diagonal garden track"),
    }
    ids = {}
    for idx, (a, b) in enumerate(pairs, start=1):
        data = dict(stairs=0, slope_pct=1.5, surface="smooth", curb="flush",
                    crossing=0, verification="verified", days_ago=2,
                    name=f"{NODE_LABELS[a-1]}–{NODE_LABELS[b-1]}")
        data.update(configs.get((a, b), {}))
        if data["verification"] == "unverified":
            data["days_ago"] = 180
        if data["verification"] == "community":
            data["days_ago"] = 21
        # Every stored edge distance is >= great-circle distance, enabling admissible A*.
        length = round(haversine(coords[f"N{a}"], coords[f"N{b}"]) * 1.08, 1)
        eid = f"E{idx:02d}"
        ids[(a, b)] = eid
        db.execute("""INSERT INTO edges(id,source,target,distance_m,stairs,slope_pct,
          surface,curb,crossing,verification,surveyed_at,name) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""", (
            eid, f"N{a}", f"N{b}", length, data["stairs"], data["slope_pct"],
            data["surface"], data["curb"], data["crossing"], data["verification"],
            iso(now - timedelta(days=data["days_ago"])), data["name"],
        ))

    reports = [
        (ids[(8, 9)], "temporary_obstruction", 3, "Synthetic demo: path occupied by construction fencing", "verified", 2),
        (ids[(17, 18)], "broken_surface", 2, "Synthetic demo: loose paving may obstruct movement", "pending", 5),
        (ids[(6, 7)], "blocked", 2, "Synthetic demo: former obstacle, now removed", "resolved", 14),
    ]
    for edge_id, obstacle, severity, description, status, ttl in reports:
        db.execute("""INSERT INTO reports(edge_id,obstacle_type,severity,description,status,
          created_at,updated_at,expires_at,reviewer_note) VALUES(?,?,?,?,?,?,?,?,?)""", (
            edge_id, obstacle, severity, description, status,
            iso(now - timedelta(hours=6)), iso(now), iso(now + timedelta(days=ttl)),
            "Synthetic moderator example" if status != "pending" else "",
        ))
