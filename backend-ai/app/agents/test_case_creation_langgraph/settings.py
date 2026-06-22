"""Project-wide settings (§2.1 of the agent spec).

Each worker's model + provider + temperature is carried by a *settings slot*
(``LLMSlot``). The slot value is everything ``build_llm()`` needs — nothing is
hard-coded in node or tool code, so swapping Azure OpenAI for Anthropic/Gemini
is a config change.

Loaded from environment / ``.env`` via pydantic-settings.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolve .env regardless of the working directory (the backend is launched
# from backend-ai/, but .env lives at the repo root). Try repo root, then cwd.
_REPO_ROOT = Path(__file__).resolve().parents[4]
_ENV_FILES = (_REPO_ROOT / ".env", ".env")


# Sensible default model per provider (used by Settings._effective_model).
_DEFAULT_MODELS = {
    "azure_openai": "gpt-4o",
    "openai": "gpt-4o",
    "anthropic": "claude-3-5-sonnet-latest",
    "google": "gemini-2.5-flash-lite",  # 2.0-flash is often limit:0; -lite is the most available free model
}


class LLMSlot(BaseModel):
    """A resolved per-worker model slot. Provider + tuning travel together."""

    provider: str = "azure_openai"  # azure_openai | openai | anthropic | google
    model: str = "gpt-4o"
    temperature: float = 0.2

    # Provider credentials/endpoints (populated by Settings below)
    api_key: str | None = None
    endpoint: str | None = None
    api_version: str | None = None

    # Dev: deterministic offline stub instead of a real provider call
    offline_stub: bool = False


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_ENV_FILES, env_file_encoding="utf-8", extra="ignore"
    )

    # ── Provider selection + credentials ──────────────────────────────────
    llm_provider: str = "azure_openai"
    azure_openai_api_key: str | None = None
    azure_openai_endpoint: str | None = None
    azure_openai_api_version: str = "2024-08-01-preview"
    anthropic_api_key: str | None = None
    google_api_key: str | None = None

    # ── Per-worker model + temperature ────────────────────────────────────
    llm_planner_model: str = "gpt-4o"
    llm_planner_temperature: float = 0.1
    llm_executor_model: str = "gpt-4o"
    llm_executor_temperature: float = 0.5
    llm_reviewer_model: str = "gpt-4o"
    llm_reviewer_temperature: float = 0.0

    # ── Observability ─────────────────────────────────────────────────────
    langchain_tracing_v2: bool = False
    langsmith_api_key: str | None = None
    langsmith_project: str = "test-case-creation"

    # ── Checkpointer ──────────────────────────────────────────────────────
    checkpointer: str = "memory"  # memory | postgres
    postgres_url: str | None = None

    # ── Guardrails ────────────────────────────────────────────────────────
    input_max_tokens: int = 8000
    injection_block_threshold: float = 0.85
    correctness_hard_gate: int = 80
    max_self_corrections: int = 2

    # ── Dev convenience ───────────────────────────────────────────────────
    llm_offline_stub: bool = True

    # ── Phase 4: external integrations (all optional) ─────────────────────
    # Absent config → the corresponding tool falls back to its synthetic stub,
    # so implementation + tests never require the live systems.
    # Requirement store (Neo4j / Azure DevOps)
    neo4j_uri: str | None = None
    neo4j_user: str | None = None
    neo4j_password: str | None = None
    ado_org_url: str | None = None
    ado_project: str | None = None
    ado_pat: str | None = None
    # Existing test suite (MongoDB)
    mongodb_uri: str | None = None
    mongodb_db: str = "qa"
    mongodb_collection: str = "test_cases"
    # Vector index (semantic dedupe)
    vector_backend: str | None = None  # e.g. "azure_search" | "pgvector"
    vector_url: str | None = None
    vector_api_key: str | None = None
    # Test-management system (writes)
    test_mgmt_kind: str | None = None  # e.g. "ado" | "zephyr" | "generic"
    test_mgmt_base_url: str | None = None
    test_mgmt_token: str | None = None
    # Jira (webhook / fetch)
    jira_base_url: str | None = None
    jira_email: str | None = None
    jira_token: str | None = None

    # ── Phase 5: governance ───────────────────────────────────────────────
    agent_version: str = "0.1.0"
    prompt_version: str = "2024-06-16"  # pin; bump deliberately for rollback control
    # Per-project feature flag. enabled_projects is a CSV allowlist; when a
    # project is not listed, default_project_enabled decides.
    enabled_projects: str = ""  # e.g. "DEMO-PROJ,TEAM-A"
    default_project_enabled: bool = True
    feature_flags_file: str | None = None  # optional JSON override {project_id: bool}

    # ── Phase 6: continuous improvement ───────────────────────────────────
    feedback_path: str = "data/feedback.jsonl"
    run_log_path: str = "data/run_log.jsonl"

    def enabled_project_set(self) -> set[str]:
        return {p.strip() for p in self.enabled_projects.split(",") if p.strip()}

    def _effective_model(self, configured: str) -> str:
        # When the model is still the cross-provider default ("gpt-4o") but the
        # provider is not OpenAI-family, pick that provider's sensible default —
        # so switching provider is a single env var (LLM_PROVIDER).
        if configured == "gpt-4o" and self.llm_provider in ("anthropic", "google"):
            return _DEFAULT_MODELS.get(self.llm_provider, configured)
        return configured

    # ── Derived per-worker slots ──────────────────────────────────────────
    def _slot(self, model: str, temperature: float) -> LLMSlot:
        provider = self.llm_provider
        api_key = {
            "azure_openai": self.azure_openai_api_key,
            "openai": self.azure_openai_api_key,
            "anthropic": self.anthropic_api_key,
            "google": self.google_api_key,
        }.get(provider)
        api_key = api_key or None  # treat empty string (unset in .env) as missing
        return LLMSlot(
            provider=provider,
            model=self._effective_model(model),
            temperature=temperature,
            api_key=api_key,
            endpoint=self.azure_openai_endpoint or None,
            api_version=self.azure_openai_api_version,
            offline_stub=self.llm_offline_stub or api_key is None,
        )

    @property
    def llm_planner(self) -> LLMSlot:
        return self._slot(self.llm_planner_model, self.llm_planner_temperature)

    @property
    def llm_executor(self) -> LLMSlot:
        return self._slot(self.llm_executor_model, self.llm_executor_temperature)

    @property
    def llm_reviewer(self) -> LLMSlot:
        return self._slot(self.llm_reviewer_model, self.llm_reviewer_temperature)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
