"""Feedback + metrics endpoints (Phase 6)."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from ..improvement import feedback, metrics

router = APIRouter()


class RatingIn(BaseModel):
    rating: Literal["up", "down"]
    comment: str | None = None


@router.post("/runs/{run_id}/feedback")
def submit_feedback(run_id: str, body: RatingIn) -> dict:
    feedback.record_rating(run_id, body.rating, body.comment)
    return {"status": "recorded", "run_id": run_id, "rating": body.rating}


@router.get("/metrics/summary")
def metrics_summary() -> dict:
    return metrics.summary()
