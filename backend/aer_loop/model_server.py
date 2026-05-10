from __future__ import annotations

import json
import os
import time
import uuid
import gc
from pathlib import Path
from typing import Any

import torch
from fastapi import FastAPI
from pydantic import BaseModel, Field
from transformers import AutoModelForCausalLM, AutoTokenizer


PROJECT_ROOT = Path(os.environ.get("AER_PROJECT_ROOT", Path(__file__).resolve().parents[2]))
MODELS_DIR = PROJECT_ROOT / "models"
MODEL_PATH = os.environ.get(
    "AER_MODEL_PATH",
    os.environ.get("AER_MODEL_PATH_7B", str(MODELS_DIR / "Qwen2.5-Coder-7B-Instruct")),
)
MODEL_ID = os.environ.get("AER_OPENAI_MODEL", "qwen2.5-coder-7b-instruct")
MAX_NEW_TOKENS = int(os.environ.get("AER_MAX_NEW_TOKENS", "512"))
DEFAULT_MODEL_MAP = {
    "qwen2.5-coder-7b-instruct": os.environ.get("AER_MODEL_PATH_7B", str(MODELS_DIR / "Qwen2.5-Coder-7B-Instruct")),
    "qwen2.5-coder-14b-instruct": os.environ.get("AER_MODEL_PATH_14B", str(MODELS_DIR / "Qwen2.5-Coder-14B-Instruct")),
}
MODEL_MAP = {**DEFAULT_MODEL_MAP, **json.loads(os.environ.get("AER_MODEL_MAP", "{}"))}

app = FastAPI(title="Team-I local OpenAI-compatible model server", version="0.1.0")
tokenizer = None
model = None
loaded_model_id = ""
loaded_model_path = ""


class ChatMessage(BaseModel):
    role: str
    content: str | list[dict[str, Any]]


class ChatRequest(BaseModel):
    model: str = MODEL_ID
    messages: list[ChatMessage]
    temperature: float = 0.2
    max_tokens: int | None = None
    stream: bool = False


class CompletionRequest(BaseModel):
    model: str = MODEL_ID
    prompt: str | list[str]
    temperature: float = 0.0
    max_tokens: int | None = None
    stream: bool = False


def _load(model_id: str = MODEL_ID) -> None:
    global tokenizer, model, loaded_model_id, loaded_model_path
    if model is not None and loaded_model_id == model_id:
        return
    if model is not None:
        del tokenizer
        del model
        tokenizer = None
        model = None
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    model_path = MODEL_MAP.get(model_id, MODEL_PATH)
    tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)
    dtype = torch.float16 if torch.cuda.is_available() else torch.float32
    model = AutoModelForCausalLM.from_pretrained(
        model_path,
        torch_dtype=dtype,
        device_map="auto" if torch.cuda.is_available() else None,
        trust_remote_code=True,
    )
    model.eval()
    loaded_model_id = model_id
    loaded_model_path = model_path


def _content_to_text(content: str | list[dict[str, Any]]) -> str:
    if isinstance(content, str):
        return content
    parts = []
    for item in content:
        if item.get("type") == "text":
            parts.append(str(item.get("text", "")))
    return "\n".join(parts)


def _generate(prompt: str, max_tokens: int | None) -> tuple[str, int, int]:
    assert tokenizer is not None and model is not None
    inputs = tokenizer(prompt, return_tensors="pt")
    if next(model.parameters()).is_cuda:
        inputs = {k: v.to(model.device) for k, v in inputs.items()}
    gen_kwargs = {
        "max_new_tokens": max_tokens or MAX_NEW_TOKENS,
        "do_sample": False,
        "pad_token_id": tokenizer.eos_token_id,
    }
    with torch.no_grad():
        out = model.generate(**inputs, **gen_kwargs)
    prompt_tokens = int(inputs["input_ids"].shape[-1])
    completion_tokens = int(out.shape[-1] - prompt_tokens)
    text = tokenizer.decode(out[0][prompt_tokens:], skip_special_tokens=True)
    return text, prompt_tokens, completion_tokens


@app.on_event("startup")
def startup() -> None:
    _load(MODEL_ID)


@app.get("/v1/models")
def models() -> dict[str, Any]:
    return {"object": "list", "data": [{"id": model_id, "object": "model", "owned_by": "team-i", "root": path} for model_id, path in MODEL_MAP.items()]}


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "ok": True,
        "loaded_model_id": loaded_model_id,
        "loaded_model_path": loaded_model_path,
        "available_models": sorted(MODEL_MAP),
        "cuda_available": torch.cuda.is_available(),
    }


@app.post("/v1/chat/completions")
def chat(body: ChatRequest) -> dict[str, Any]:
    _load(body.model)
    messages = [{"role": m.role, "content": _content_to_text(m.content)} for m in body.messages]
    if hasattr(tokenizer, "apply_chat_template"):
        prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    else:
        prompt = "\n".join([f"{m['role']}: {m['content']}" for m in messages]) + "\nassistant:"
    text, prompt_tokens, completion_tokens = _generate(prompt, body.max_tokens)
    created = int(time.time())
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
        "object": "chat.completion",
        "created": created,
        "model": body.model,
        "choices": [{"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens, "total_tokens": prompt_tokens + completion_tokens},
    }


@app.post("/v1/completions")
def completion(body: CompletionRequest) -> dict[str, Any]:
    _load(body.model)
    prompt = body.prompt[0] if isinstance(body.prompt, list) else body.prompt
    text, prompt_tokens, completion_tokens = _generate(prompt, body.max_tokens)
    created = int(time.time())
    return {
        "id": f"cmpl-{uuid.uuid4().hex[:12]}",
        "object": "text_completion",
        "created": created,
        "model": body.model,
        "choices": [{"index": 0, "text": text, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens, "total_tokens": prompt_tokens + completion_tokens},
    }
