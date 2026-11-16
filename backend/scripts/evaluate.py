"""Run from backend/: python scripts/evaluate.py"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.db import connect, database_path, initialize
from app.evaluation import calculate_evaluation
from app.graph import load_network

initialize()
with connect(database_path()) as db:
    result = calculate_evaluation(load_network(db))
print(json.dumps({k: v for k, v in result.items() if k != "cases"}, indent=2))
