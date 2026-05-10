from __future__ import annotations

import argparse
from pathlib import Path

from huggingface_hub import snapshot_download


MODEL_SPECS = {
    "7b": {
        "repo_id": "Qwen/Qwen2.5-Coder-7B-Instruct",
        "target": "Qwen2.5-Coder-7B-Instruct",
    },
    "14b": {
        "repo_id": "Qwen/Qwen2.5-Coder-14B-Instruct",
        "target": "Qwen2.5-Coder-14B-Instruct",
    },
}


def download_model(model_key: str, models_dir: Path, revision: str | None, resume: bool) -> Path:
    spec = MODEL_SPECS[model_key]
    target = models_dir / spec["target"]
    target.mkdir(parents=True, exist_ok=True)
    kwargs = {
        "repo_id": spec["repo_id"],
        "local_dir": str(target),
        "resume_download": resume,
    }
    if revision:
        kwargs["revision"] = revision
    snapshot_download(**kwargs)
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description="Download Team-I local model weights from Hugging Face.")
    parser.add_argument("--model", choices=["7b", "14b", "all"], default="7b")
    parser.add_argument("--models-dir", type=Path, default=Path("models"))
    parser.add_argument("--revision", default=None)
    parser.add_argument("--resume", action="store_true", help="Resume an interrupted download when supported.")
    args = parser.parse_args()

    keys = ["7b", "14b"] if args.model == "all" else [args.model]
    args.models_dir.mkdir(parents=True, exist_ok=True)
    for key in keys:
        target = download_model(key, args.models_dir, args.revision, args.resume)
        print(f"{key}: {target.resolve()}")


if __name__ == "__main__":
    main()
