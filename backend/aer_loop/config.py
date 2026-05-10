from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _project_root() -> Path:
    return Path(os.environ.get("AER_PROJECT_ROOT", Path(__file__).resolve().parents[2]))


def _model_path(name: str) -> str:
    return str(_project_root() / "models" / name)


@dataclass(frozen=True)
class Settings:
    project_root: Path = _project_root()
    data_dir: Path = _project_root() / "runtime" / "data"
    artifact_dir: Path = _project_root() / "runtime" / "artifacts"
    log_dir: Path = _project_root() / "logs"
    db_path: Path = Path(os.environ.get("AER_DB_PATH", _project_root() / "runtime" / "aer_loop.sqlite"))
    model_backend: str = os.environ.get("AER_MODEL_BACKEND", "fallback")
    model_path: str = os.environ.get(
        "AER_MODEL_PATH",
        os.environ.get("AER_MODEL_PATH_7B", _model_path("Qwen2.5-Coder-7B-Instruct")),
    )
    openai_base_url: str = os.environ.get("AER_OPENAI_BASE_URL", "")
    openai_api_key: str = os.environ.get("AER_OPENAI_API_KEY", "EMPTY")
    openai_model: str = os.environ.get("AER_OPENAI_MODEL", "qwen2.5-coder-7b-instruct")
    assertion_model: str = os.environ.get("AER_ASSERTION_MODEL", "qwen2.5-coder-7b-instruct")
    router_model: str = os.environ.get("AER_ROUTER_MODEL", "qwen2.5-coder-7b-instruct")
    investigation_model: str = os.environ.get("AER_INVESTIGATION_MODEL", "qwen2.5-coder-7b-instruct")
    counter_model: str = os.environ.get("AER_COUNTER_MODEL", "qwen2.5-coder-7b-instruct")
    passport_model: str = os.environ.get("AER_PASSPORT_MODEL", "qwen2.5-coder-14b-instruct")
    pattern_model: str = os.environ.get("AER_PATTERN_MODEL", "qwen2.5-coder-14b-instruct")
    embedding_model_path: str = os.environ.get("AER_EMBEDDING_MODEL_PATH", _model_path("Qwen3-Embedding-8B"))
    reranker_model_path: str = os.environ.get("AER_RERANKER_MODEL_PATH", _model_path("Qwen3-Reranker-8B"))
    openclaw_gateway_url: str = os.environ.get("AER_OPENCLAW_GATEWAY_URL", "http://127.0.0.1:18789")
    openclaw_token: str = os.environ.get("AER_OPENCLAW_TOKEN", "")
    max_new_tokens: int = int(os.environ.get("AER_MAX_NEW_TOKENS", "384"))
    seed: int = int(os.environ.get("AER_SEED", "20260510"))
    demo_order_count: int = int(os.environ.get("AER_DEMO_ORDER_COUNT", "25000"))


settings = Settings()


def ensure_runtime_dirs() -> None:
    for path in (settings.data_dir, settings.artifact_dir, settings.log_dir, settings.db_path.parent):
        path.mkdir(parents=True, exist_ok=True)
