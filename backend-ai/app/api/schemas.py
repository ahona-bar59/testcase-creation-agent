"""API request/response models (mirror the spec's input contract §1.4)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class RunOptions(BaseModel):
    priority: Literal["High", "Medium", "Low"] | None = None
    includeEdgeCases: bool = True
    testTypes: list[Literal["Positive", "Negative", "Edge", "Boundary"]] | None = None


class RunRequest(BaseModel):
    """Maps onto TestCaseCreationInput (§1.4)."""

    userStory: str
    acceptanceCriteria: str | None = None
    projectId: str
    jiraStoryId: str | None = None
    trigger_type: Literal["manual", "api", "webhook"] = "manual"
    options: RunOptions | None = None

    def to_payload(self) -> dict:
        return {
            "userStory": self.userStory,
            "acceptanceCriteria": self.acceptanceCriteria or "",
            "projectId": self.projectId,
            "jiraStoryId": self.jiraStoryId,
            "trigger_type": self.trigger_type,
            "options": self.options.model_dump(exclude_none=True) if self.options else {},
        }


class RunCreated(BaseModel):
    run_id: str
    stream_url: str = Field(description="Connect a WebSocket here to drive the run.")


class HitlResponse(BaseModel):
    """Client → server message answering a `hitl` pause."""

    type: Literal["hitl_response"] = "hitl_response"
    choice: str
    test_cases_edited: list[dict] | None = None
