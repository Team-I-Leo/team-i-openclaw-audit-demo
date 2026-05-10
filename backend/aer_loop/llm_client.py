from __future__ import annotations

import json
import os
import re
import ast
import gc
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib import request as urlrequest

from .config import settings


def _strip_code_fence(text: str) -> str:
    text = text.strip()
    fenced = re.match(r"^```(?:json|JSON)?\s*(.*?)\s*```$", text, flags=re.DOTALL)
    if fenced:
        return fenced.group(1).strip()
    text = re.sub(r"^\s*```(?:json|JSON)?\s*", "", text).strip()
    text = re.sub(r"\s*```\s*$", "", text).strip()
    return text


def _first_balanced_object(text: str) -> str | None:
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    in_string = False
    escaped = False
    for idx in range(start, len(text)):
        char = text[idx]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : idx + 1]
    return text[start:]


def _safe_eval_number(node: ast.AST) -> float:
    if isinstance(node, ast.Expression):
        return _safe_eval_number(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        value = _safe_eval_number(node.operand)
        return value if isinstance(node.op, ast.UAdd) else -value
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div)):
        left = _safe_eval_number(node.left)
        right = _safe_eval_number(node.right)
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if right == 0:
            raise ValueError("division by zero")
        return left / right
    raise ValueError("unsupported numeric expression")


def _repair_numeric_expressions(candidate: str) -> str:
    def repl(match: re.Match[str]) -> str:
        expr = match.group(1).strip()
        suffix = match.group(2)
        if not re.search(r"[+\-*/()]", expr):
            return match.group(0)
        if not re.fullmatch(r"[0-9eE.\s+\-*/()]+", expr):
            return match.group(0)
        try:
            value = _safe_eval_number(ast.parse(expr, mode="eval"))
        except Exception:
            return match.group(0)
        return f": {round(value, 6)}{suffix}"

    return re.sub(r":\s*([0-9eE.\s+\-*/()]+)(\s*[,}])", repl, candidate)


def _strip_line_comments(candidate: str) -> str:
    return "\n".join(re.sub(r"\s+//.*$", "", line) for line in candidate.splitlines())


def extract_json_object(text: str) -> dict[str, Any] | None:
    text = _strip_code_fence(text)
    if not text:
        return None
    candidates = [text]
    balanced = _first_balanced_object(text)
    if balanced and balanced != text:
        candidates.append(balanced)
    for candidate in list(candidates):
        uncommented = _strip_line_comments(candidate)
        if uncommented != candidate:
            candidates.append(uncommented)
            candidate = uncommented
        repaired = _repair_numeric_expressions(candidate)
        if repaired != candidate:
            candidates.append(repaired)
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
            return parsed if isinstance(parsed, dict) else None
        except Exception:
            pass
    return None


@dataclass
class LLMResult:
    text: str
    parsed_json: dict[str, Any] | None
    backend: str
    model: str
    used_fallback: bool = False


class LLMClient:
    _LOCAL_CACHE: OrderedDict[str, tuple[Any, Any]] = OrderedDict()

    def __init__(self, backend: str | None = None, model: str | None = None, role: str = "generic"):
        self.backend = backend or settings.model_backend
        self.model = model or settings.openai_model
        self.role = role

    def generate_json(self, system: str, user: str, fallback: dict[str, Any]) -> LLMResult:
        user = self._fit_prompt(user)
        if self.backend == "openai":
            return self._generate_openai(system, user, fallback)
        if self.backend == "local":
            return self._generate_local(system, user, fallback)
        return LLMResult(
            text=json.dumps(fallback, ensure_ascii=False),
            parsed_json=fallback,
            backend="fallback",
            model="deterministic-fallback",
            used_fallback=True,
        )

    def _fit_prompt(self, text: str) -> str:
        max_chars = 52000
        if len(text) <= max_chars:
            return text
        head = text[:8000]
        tail = text[-(max_chars - len(head) - 1200) :]
        return f"{head}\n\n...[prompt truncated for local model context]...\n\n{tail}"

    def _generate_openai(self, system: str, user: str, fallback: dict[str, Any]) -> LLMResult:
        try:
            endpoint = settings.openai_base_url.rstrip("/") + "/chat/completions"
            payload = {
                "model": self.model,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                "temperature": 0.2,
                "max_tokens": settings.max_new_tokens,
            }
            req = urlrequest.Request(
                endpoint,
                data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {settings.openai_api_key}"},
                method="POST",
            )
            timeout = int(os.environ.get("AER_OPENAI_TIMEOUT", "900"))
            with urlrequest.urlopen(req, timeout=timeout) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            text = body["choices"][0]["message"]["content"] or ""
            parsed = extract_json_object(text)
            if parsed is None:
                return LLMResult(text=text, parsed_json=fallback, backend="openai", model=self.model, used_fallback=True)
            return LLMResult(text=text, parsed_json=parsed, backend="openai", model=self.model)
        except Exception as exc:
            fallback = {**fallback, "model_error": str(exc)[:300]}
            return LLMResult(
                text=json.dumps(fallback, ensure_ascii=False),
                parsed_json=fallback,
                backend="openai-error",
                model=self.model,
                used_fallback=True,
            )

    def _generate_local(self, system: str, user: str, fallback: dict[str, Any]) -> LLMResult:
        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer

            model_path = self._resolve_local_model_path()
            cached = self._LOCAL_CACHE.get(model_path)
            if cached:
                tokenizer, model = cached
                self._LOCAL_CACHE.move_to_end(model_path)
            else:
                self._prepare_cache_slot(model_path)
                tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)
                dtype = torch.float16 if torch.cuda.is_available() else torch.float32
                model = AutoModelForCausalLM.from_pretrained(
                    model_path,
                    torch_dtype=dtype,
                    device_map="auto" if torch.cuda.is_available() else None,
                    trust_remote_code=True,
                )
                model.eval()
                self._cache_local_model(model_path, tokenizer, model)
            messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
            if hasattr(tokenizer, "apply_chat_template"):
                prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
            else:
                prompt = f"System: {system}\nUser: {user}\nAssistant:"
            inputs = tokenizer(prompt, return_tensors="pt")
            if next(model.parameters()).is_cuda:
                inputs = {k: v.to(model.device) for k, v in inputs.items()}
            with torch.no_grad():
                out = model.generate(
                    **inputs,
                    max_new_tokens=settings.max_new_tokens,
                    do_sample=False,
                    pad_token_id=tokenizer.eos_token_id,
                )
            text = tokenizer.decode(out[0][inputs["input_ids"].shape[-1] :], skip_special_tokens=True)
            parsed = extract_json_object(text)
            if parsed is None:
                return LLMResult(text=text, parsed_json=fallback, backend="local", model=model_path, used_fallback=True)
            return LLMResult(text=text, parsed_json=parsed, backend="local", model=model_path)
        except Exception as exc:
            fallback = {**fallback, "model_error": str(exc)[:300]}
            return LLMResult(
                text=json.dumps(fallback, ensure_ascii=False),
                parsed_json=fallback,
                backend="local-error",
                model=self.model or settings.model_path,
                used_fallback=True,
            )

    def _resolve_local_model_path(self) -> str:
        model = self.model or settings.model_path
        if self._is_model_path_ready(model):
            return str(Path(model))
        project_models = settings.project_root / "models"
        candidates = {
            "qwen2.5-coder-7b-instruct": [
                os.environ.get("AER_MODEL_PATH_7B"),
                settings.model_path,
                str(project_models / "Qwen2.5-Coder-7B-Instruct"),
            ],
            "qwen2.5-coder-14b-instruct": [
                os.environ.get("AER_MODEL_PATH_14B"),
                str(project_models / "Qwen2.5-Coder-14B-Instruct"),
            ],
            "qwen2.5-14b-instruct": [
                os.environ.get("AER_MODEL_PATH_14B"),
                str(project_models / "Qwen2.5-14B-Instruct"),
            ],
        }
        for candidate in candidates.get(model.lower(), []):
            if candidate and self._is_model_path_ready(candidate):
                return str(Path(candidate))
        return settings.model_path

    def _is_model_path_ready(self, path: str | os.PathLike[str]) -> bool:
        root = Path(path)
        if not root.exists() or not root.is_dir():
            return False
        if not (root / "config.json").exists():
            return False
        if any(root.rglob("*.incomplete")):
            return False
        weights = list(root.glob("*.safetensors")) + list(root.glob("*.bin"))
        if not weights:
            return False
        shard_matches = []
        for weight in weights:
            match = re.search(r"-(\d{5})-of-(\d{5})\.(?:safetensors|bin)$", weight.name)
            if match:
                shard_matches.append((int(match.group(1)), int(match.group(2))))
        if shard_matches:
            expected = max(total for _, total in shard_matches)
            present = {idx for idx, total in shard_matches if total == expected}
            return all(idx in present for idx in range(1, expected + 1))
        return True

    @classmethod
    def _prepare_cache_slot(cls, model_path: str) -> None:
        if model_path in cls._LOCAL_CACHE:
            return
        limit = max(1, int(os.environ.get("AER_LOCAL_MODEL_CACHE_SIZE", "1")))
        while len(cls._LOCAL_CACHE) >= limit:
            cls._drop_oldest_local_model()

    @classmethod
    def _cache_local_model(cls, model_path: str, tokenizer: Any, model: Any) -> None:
        cls._LOCAL_CACHE[model_path] = (tokenizer, model)
        cls._LOCAL_CACHE.move_to_end(model_path)
        limit = max(1, int(os.environ.get("AER_LOCAL_MODEL_CACHE_SIZE", "1")))
        while len(cls._LOCAL_CACHE) > limit:
            cls._drop_oldest_local_model()

    @classmethod
    def _drop_oldest_local_model(cls) -> None:
        _, (old_tokenizer, old_model) = cls._LOCAL_CACHE.popitem(last=False)
        del old_tokenizer
        del old_model
        gc.collect()
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass
