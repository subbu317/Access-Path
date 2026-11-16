from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.db import connect, initialize
from app.graph import load_network
from app.main import create_app


@pytest.fixture
def db_path(tmp_path: Path):
    path = tmp_path / "test.db"
    initialize(path)
    return path


@pytest.fixture
def graph(db_path):
    with connect(db_path) as db:
        return load_network(db)


@pytest.fixture
def client(db_path):
    with TestClient(create_app(db_path)) as c:
        yield c
