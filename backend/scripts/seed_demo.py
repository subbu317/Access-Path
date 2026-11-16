"""Run from backend/: python scripts/seed_demo.py --reset"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.db import connect, database_path, initialize
from app.demo_data import seed

parser = argparse.ArgumentParser(description="Reset or initialize a synthetic AccessPath demo network")
parser.add_argument("--reset", action="store_true", help="Delete all demo records and rebuild; irreversible")
args = parser.parse_args()
path = database_path()
initialize(path)
if args.reset:
    with connect(path) as db:
        for table in ("moderation_audit", "reports", "route_requests", "evaluation_runs", "edges", "nodes"):
            db.execute(f"DELETE FROM {table}")
        db.execute("UPDATE settings SET value=CAST(value AS INTEGER)+1 WHERE key='network_revision'")
        seed(db)
print(f"Synthetic demo seeded at {path}. Reset={args.reset}")
