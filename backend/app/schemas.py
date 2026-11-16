"""Request validation and public API contracts."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Profile = Literal["wheelchair", "walker", "step_free", "pedestrian"]
Algorithm = Literal["astar", "dijkstra"]
Obstacle = Literal["blocked", "stairs", "steep_slope", "broken_surface", "missing_curb", "temporary_obstruction"]
Action = Literal["review", "verify", "reject", "resolve", "expire"]


class RouteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,24}$")
    end_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,24}$")
    profile: Profile = "wheelchair"
    algorithm: Algorithm = "astar"
    risk_aversion: int = Field(70, ge=0, le=100)
    alternatives: int = Field(3, ge=1, le=5)


class ReportCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    edge_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,24}$")
    obstacle_type: Obstacle
    severity: int = Field(2, ge=1, le=3)
    description: str = Field(min_length=8, max_length=500)
    expires_in_days: int = Field(7, ge=1, le=90)


class ModerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Action
    note: str = Field("", max_length=500)
