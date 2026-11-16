"""AccessPath REST API. All demo data is synthetic, local-first, and anonymous."""
from __future__ import annotations

import json
import os
import secrets
from datetime import timedelta
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from .db import connect, database_path, increment_revision, initialize, iso, utcnow
from .evaluation import calculate_evaluation
from .graph import geojson, load_network, network_payload
from .routing import PROFILES, plan_route
from .schemas import ModerateRequest, ReportCreate, RouteRequest


def create_app(db_path: Path | str | None = None) -> FastAPI:
    path = Path(db_path or database_path())
    initialize(path)
    application = FastAPI(title="AccessPath API", version="1.0.0",
                          description="Synthetic, confidence-aware pedestrian routing research demo")
    allowed = [s.strip() for s in os.getenv(
        "ACCESSPATH_CORS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if s.strip()]
    application.add_middleware(CORSMiddleware, allow_origins=allowed,
                               allow_credentials=False, allow_methods=["GET", "POST"],
                               allow_headers=["Content-Type", "X-Admin-Key"])

    def admin_key(x_admin_key: str | None = Header(default=None)):
        secret = os.getenv("ACCESSPATH_ADMIN_KEY", "demo-admin-key")
        if not x_admin_key or not secrets.compare_digest(x_admin_key, secret):
            raise HTTPException(status_code=403, detail="Invalid admin key")

    @application.get("/health")
    def health():
        return {"ok": True, "name": "AccessPath", "mode": "synthetic-demo"}

    @application.get("/api/profiles")
    def profiles():
        return PROFILES

    @application.get("/api/network")
    def network():
        with connect(path) as db:
            return network_payload(load_network(db))

    @application.get("/api/network.geojson")
    def export_geojson():
        with connect(path) as db:
            return geojson(load_network(db))

    @application.post("/api/routes")
    def routes(payload: RouteRequest):
        if payload.start_id == payload.end_id:
            raise HTTPException(422, "Start and destination must be different")
        with connect(path) as db:
            graph = load_network(db)
            if payload.start_id not in graph.nodes or payload.end_id not in graph.nodes:
                raise HTTPException(404, "Start or destination does not exist in the demo network")
            result = plan_route(graph, payload.start_id, payload.end_id,
                                payload.profile, payload.algorithm,
                                payload.risk_aversion, payload.alternatives)
            chosen = result["routes"][0] if result["routes"] else None
            db.execute("""INSERT INTO route_requests(start_id,end_id,profile,algorithm,risk_aversion,
              shortest_distance_m,selected_distance_m,selected_confidence,computation_ms,network_revision,created_at)
              VALUES(?,?,?,?,?,?,?,?,?,?,?)""", (
                payload.start_id, payload.end_id, payload.profile, payload.algorithm,
                payload.risk_aversion,
                result["shortest"]["distance_m"] if result["shortest"] else None,
                chosen["distance_m"] if chosen else None,
                chosen["confidence"] if chosen else None,
                result["computation_ms"], graph.revision, iso(),
            ))
            return result

    @application.get("/api/reports")
    def reports(status: str | None = None):
        if status and status not in ("pending", "reviewed", "verified", "resolved", "expired", "rejected"):
            raise HTTPException(422, "Unknown report status")
        with connect(path) as db:
            load_network(db)  # expire outdated reports before displaying
            if status:
                rows = db.execute("SELECT * FROM reports WHERE status=? ORDER BY id DESC LIMIT 200", (status,))
            else:
                rows = db.execute("SELECT * FROM reports ORDER BY id DESC LIMIT 200")
            return {"reports": [dict(r) for r in rows]}

    @application.post("/api/reports", status_code=201)
    def report_obstacle(payload: ReportCreate):
        description = payload.description.strip()
        if len(description) < 8:
            raise HTTPException(422, "Description needs at least 8 non-whitespace characters")
        now = utcnow()
        with connect(path) as db:
            if not db.execute("SELECT 1 FROM edges WHERE id=?", (payload.edge_id,)).fetchone():
                raise HTTPException(404, "Unknown network segment")
            cursor = db.execute("""INSERT INTO reports(edge_id,obstacle_type,severity,description,
             status,created_at,updated_at,expires_at) VALUES(?,?,?,?,?,?,?,?)""", (
                payload.edge_id, payload.obstacle_type, payload.severity,
                description, "pending", iso(now), iso(now), iso(now + timedelta(days=payload.expires_in_days)),
            ))
            increment_revision(db)  # pending reports change uncertainty penalties
            record = db.execute("SELECT * FROM reports WHERE id=?", (cursor.lastrowid,)).fetchone()
            return {"report": dict(record), "message": "Pending review; not a verified obstacle"}

    @application.post("/api/admin/reports/{report_id}/moderate", dependencies=[Depends(admin_key)])
    def moderate_report(report_id: int, payload: ModerateRequest):
        transitions = {
            "pending": {"review": "reviewed", "verify": "verified", "reject": "rejected", "expire": "expired"},
            "reviewed": {"verify": "verified", "reject": "rejected", "expire": "expired"},
            "verified": {"resolve": "resolved", "expire": "expired"},
        }
        with connect(path) as db:
            record = db.execute("SELECT * FROM reports WHERE id=?", (report_id,)).fetchone()
            if not record:
                raise HTTPException(404, "Report not found")
            status = transitions.get(record["status"], {}).get(payload.action)
            if not status:
                raise HTTPException(409, f"Cannot {payload.action} a {record['status']} report")
            db.execute("UPDATE reports SET status=?,reviewer_note=?,updated_at=? WHERE id=?",
                       (status, payload.note.strip(), iso(), report_id))
            db.execute("INSERT INTO moderation_audit(report_id,action,note,occurred_at) VALUES(?,?,?,?)",
                       (report_id, payload.action, payload.note.strip(), iso()))
            increment_revision(db)
            return {"report": dict(db.execute("SELECT * FROM reports WHERE id=?", (report_id,)).fetchone())}

    @application.get("/api/admin/overview", dependencies=[Depends(admin_key)])
    def admin_overview():
        with connect(path) as db:
            load_network(db)
            counts = {r["status"]: r["total"] for r in db.execute(
                "SELECT status,COUNT(*) total FROM reports GROUP BY status")}
            requests = db.execute("SELECT COUNT(*) AS count FROM route_requests").fetchone()["count"]
            recent = [dict(r) for r in db.execute(
                "SELECT * FROM moderation_audit ORDER BY id DESC LIMIT 12")]
            return {"status_counts": counts, "anonymous_route_requests": requests,
                    "audit": recent, "demo_admin_key_warning": "Local demo key only; configure authentication before any public deployment."}

    @application.post("/api/evaluations/run", dependencies=[Depends(admin_key)])
    def run_evaluation():
        with connect(path) as db:
            graph = load_network(db)
            result = calculate_evaluation(graph)
            cursor = db.execute("INSERT INTO evaluation_runs(created_at,network_revision,results_json) VALUES(?,?,?)",
                                (iso(), graph.revision, json.dumps(result)))
            return {"id": cursor.lastrowid, "results": result}

    @application.get("/api/evaluations")
    def evaluations(limit: int = Query(5, ge=1, le=20)):
        with connect(path) as db:
            rows = db.execute("SELECT * FROM evaluation_runs ORDER BY id DESC LIMIT ?", (limit,))
            return {"runs": [{"id": r["id"], "created_at": r["created_at"],
                              "network_revision": r["network_revision"],
                              "results": json.loads(r["results_json"])} for r in rows]}

    return application


app = create_app()
