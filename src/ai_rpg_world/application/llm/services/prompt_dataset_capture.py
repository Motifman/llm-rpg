"""LLM request/response の prompt dataset 用キャプチャ。

Phase 1 は実験中の追記保存だけを担当する。Hugging Face 向け Parquet export は
後続 Phase 2 に分ける。
"""

from __future__ import annotations

import copy
import hashlib
import json
import logging
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Optional


SCHEMA_VERSION = 1
_SAMPLING_PARAMETER_KEYS = ("temperature", "top_p", "max_tokens", "seed")
_SECRET_REQUEST_KEYS = frozenset({"api_key", "headers", "authorization"})
_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PromptDatasetCallContext:
    """1 LLM 呼び出しの dataset 保存文脈。

    ``being_id`` / ``persona_id`` は capture 有効時に必須。取得できない場合は、
    呼び出し側がこの context を作らず fail-fast する。
    """

    llm_call_id: str
    run_id: str
    world_id: Optional[int]
    being_id: str
    player_id: int
    persona_id: str
    character_name: str
    turn_index: int
    attempt_index: int = 0
    parent_attempt_id: Optional[str] = None
    world_tick: Optional[int] = None
    time_of_day: Optional[dict[str, Any]] = None
    provenance: Optional[dict[str, Any]] = None
    reasoning_effort: Optional[str] = None
    prompt_sections: Optional[list[dict[str, Any]]] = None


def new_llm_call_id() -> str:
    """dataset と trace の結合に使う UUID 文字列を発行する。"""

    return str(uuid.uuid4())


def canonicalize_request(request: Mapping[str, Any]) -> dict[str, Any]:
    """request hash 計算用に JSON 化可能な正規形へ変換する。"""

    value = _to_jsonable(request)
    if not isinstance(value, dict):
        raise TypeError("request must canonicalize to dict")
    return value


def compute_request_hash(request: Mapping[str, Any]) -> str:
    """canonical request の sha256 を返す。"""

    canonical = canonicalize_request(request)
    raw = json.dumps(
        canonical,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "request:sha256:" + hashlib.sha256(raw).hexdigest()


def reconstruct_request(
    call: Mapping[str, Any],
    system_prompts_by_id: Mapping[str, Mapping[str, Any]],
    toolsets_by_id: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """参照化された system prompt / tools を戻し、再送可能な kwargs を復元する。

    ``api_key`` は復元しない。replay 実行時に runtime secret から注入する。
    """

    request_payload = call["request"]
    if isinstance(request_payload, str):
        request_payload = json.loads(request_payload)
    request = copy.deepcopy(request_payload["kwargs"])
    messages = []
    for message in request.get("messages", []):
        if not isinstance(message, dict):
            messages.append(message)
            continue
        restored = dict(message)
        content_ref = restored.pop("content_ref", None)
        if content_ref is not None:
            prompt_row = system_prompts_by_id[content_ref]
            restored["content"] = prompt_row["content"]
        messages.append(restored)
    request["messages"] = messages
    tools_ref = request.pop("tools_ref", None)
    if tools_ref is not None:
        tools = toolsets_by_id[tools_ref]["tools"]
        if isinstance(tools, str):
            tools = json.loads(tools)
        request["tools"] = copy.deepcopy(tools)
    return request


class PromptDatasetCaptureSink:
    """run dir 配下に prompt dataset 生 JSONL を追記する sink。"""

    def __init__(
        self,
        *,
        run_dir: Path,
        run_id: str,
        run_metadata: Mapping[str, Any],
        failure_policy: str = "fail",
    ) -> None:
        if failure_policy not in {"fail", "warn"}:
            raise ValueError(
                "PROMPT_DATASET_CAPTURE_FAILURE_POLICY must be 'fail' or 'warn'"
            )
        self.run_dir = Path(run_dir)
        self.dataset_dir = self.run_dir / "prompt_dataset"
        self.run_id = run_id
        self.failure_policy = failure_policy
        self._lock = threading.Lock()
        self._system_prompt_ids_seen: set[str] = set()
        self._toolset_ids_seen: set[str] = set()
        self._capture_incomplete = False
        self._run_metadata = dict(run_metadata)
        self._initialize()

    def _initialize(self) -> None:
        self.dataset_dir.mkdir(parents=True, exist_ok=True)
        (self.dataset_dir / "schema_version.txt").write_text(
            f"{SCHEMA_VERSION}\n", encoding="utf-8"
        )
        run_payload = {
            "schema_version": SCHEMA_VERSION,
            "run_id": self.run_id,
            **_to_jsonable(self._run_metadata),
        }
        self._write_json(self.dataset_dir / "run.json", run_payload)
        self._write_capture_status(capture_incomplete=False)

    def record_call(
        self,
        *,
        context: PromptDatasetCallContext,
        request_kwargs: Mapping[str, Any],
        response: Any = None,
        error: Optional[BaseException] = None,
        output: Optional[Mapping[str, Any]] = None,
        metrics: Optional[Mapping[str, Any]] = None,
    ) -> None:
        """1 LLM 呼び出しの request/response を `calls.jsonl` に保存する。"""

        self._handle_failure(
            lambda: self._record_call_impl(
                context=context,
                request_kwargs=request_kwargs,
                response=response,
                error=error,
                output=output,
                metrics=metrics,
            )
        )

    def record_turn_result(
        self,
        *,
        llm_call_id: str,
        run_id: str,
        world_tick: Optional[int],
        player_id: int,
        result: Mapping[str, Any],
        trace_refs: Optional[Mapping[str, Any]] = None,
    ) -> None:
        """Phase B の action 実行結果を `turn_results.jsonl` に保存する。"""

        def _write() -> None:
            payload = {
                "schema_version": SCHEMA_VERSION,
                "llm_call_id": llm_call_id,
                "run_id": run_id,
                "world_tick": world_tick,
                "player_id": player_id,
                "result": _to_jsonable(result),
                "trace_refs": _to_jsonable(trace_refs or {}),
            }
            with self._lock:
                self._append_jsonl(self.dataset_dir / "turn_results.jsonl", payload)

        self._handle_failure(_write)

    def _record_call_impl(
        self,
        *,
        context: PromptDatasetCallContext,
        request_kwargs: Mapping[str, Any],
        response: Any,
        error: Optional[BaseException],
        output: Optional[Mapping[str, Any]],
        metrics: Optional[Mapping[str, Any]],
    ) -> None:
        prepared = self._prepare_request(context, request_kwargs)
        response_payload: dict[str, Any]
        if error is not None:
            response_payload = {
                "raw": None,
                "raw_sha256": None,
                "error": _error_payload(error),
            }
        else:
            response_raw = _to_jsonable(response)
            response_payload = {
                "raw": response_raw,
                "raw_sha256": _sha256_json(response_raw),
            }
        row = {
            "schema_version": SCHEMA_VERSION,
            "llm_call_id": context.llm_call_id,
            "run_id": context.run_id,
            "world_id": context.world_id,
            "being_id": context.being_id,
            "player_id": context.player_id,
            "persona_id": context.persona_id,
            "character_name": context.character_name,
            "turn_index": context.turn_index,
            "attempt_index": context.attempt_index,
            "parent_attempt_id": context.parent_attempt_id,
            "timestamp_utc": _utc_now_iso(),
            "world_tick": context.world_tick,
            "time_of_day": _to_jsonable(context.time_of_day),
            "provenance": _to_jsonable(context.provenance or {}),
            "model": prepared["model"],
            "request": prepared["request"],
            "prompt": prepared["prompt"],
            "response": response_payload,
            "output": _to_jsonable(output or {}),
            "metrics": _to_jsonable(metrics or {}),
            "trace_refs": {},
        }
        with self._lock:
            for system_prompt in prepared["system_prompts"]:
                prompt_id = system_prompt["system_prompt_id"]
                if prompt_id not in self._system_prompt_ids_seen:
                    self._append_jsonl(
                        self.dataset_dir / "system_prompts.jsonl", system_prompt
                    )
                    self._system_prompt_ids_seen.add(prompt_id)
            toolset = prepared["toolset"]
            toolset_id = toolset["toolset_id"]
            if toolset_id not in self._toolset_ids_seen:
                self._append_jsonl(self.dataset_dir / "toolsets.jsonl", toolset)
                self._toolset_ids_seen.add(toolset_id)
            self._append_jsonl(self.dataset_dir / "calls.jsonl", row)

    def _prepare_request(
        self,
        context: PromptDatasetCallContext,
        request_kwargs: Mapping[str, Any],
    ) -> dict[str, Any]:
        kwargs = copy.deepcopy(dict(request_kwargs))
        for secret_key in tuple(kwargs):
            if str(secret_key).lower() in _SECRET_REQUEST_KEYS:
                kwargs.pop(secret_key, None)
        if "api_base" in kwargs:
            kwargs["api_base"] = _mask_api_base(kwargs.get("api_base"))

        system_prompts: list[dict[str, Any]] = []
        request_messages: list[dict[str, Any]] = []
        prompt_messages: list[dict[str, Any]] = []
        for message in kwargs.get("messages", []):
            if not isinstance(message, dict):
                request_messages.append(_to_jsonable(message))
                prompt_messages.append(_to_jsonable(message))
                continue
            request_message = copy.deepcopy(message)
            prompt_message = copy.deepcopy(message)
            if request_message.get("role") == "system":
                content = request_message.get("content")
                if not isinstance(content, str):
                    raise ValueError("system message content must be str")
                prompt_id = _id_with_hash("system_prompt", content)
                system_prompts.append(
                    {
                        "schema_version": SCHEMA_VERSION,
                        "system_prompt_id": prompt_id,
                        "system_prompt_sha256": prompt_id.removeprefix(
                            "system_prompt:sha256:"
                        ),
                        "persona_id": context.persona_id,
                        "character_name": context.character_name,
                        "player_id": context.player_id,
                        "being_id": context.being_id,
                        "prompt_builder_version": "default_prompt_builder:v1",
                        "content": content,
                        "chars": len(content),
                        "tokens": None,
                        "first_seen_llm_call_id": context.llm_call_id,
                    }
                )
                request_message.pop("content", None)
                request_message["content_ref"] = prompt_id
                prompt_message.pop("content", None)
                prompt_message["content_ref"] = prompt_id
            request_messages.append(_to_jsonable(request_message))
            prompt_messages.append(_to_jsonable(prompt_message))
        kwargs["messages"] = request_messages

        tools = kwargs.pop("tools", [])
        toolset_id = _id_with_hash("toolset", _canonical_json_bytes(tools))
        kwargs["tools_ref"] = toolset_id
        toolset = {
            "schema_version": SCHEMA_VERSION,
            "toolset_id": toolset_id,
            "toolset_sha256": toolset_id.removeprefix("toolset:sha256:"),
            "tool_names": _tool_names(tools),
            "tools": _to_jsonable(tools),
            "chars": len(json.dumps(_to_jsonable(tools), ensure_ascii=False)),
            "first_seen_llm_call_id": context.llm_call_id,
        }
        request_hash = compute_request_hash(kwargs)
        client_kind = "stub" if kwargs.get("model") == "stub" else "litellm"
        request = {
            "capture_boundary": (
                "stub.invoke" if client_kind == "stub" else "litellm.completion_kwargs"
            ),
            "request_hash": request_hash,
            "kwargs": _to_jsonable(kwargs),
            "omitted_secret_keys": ["api_key"]
            if "api_key" in request_kwargs
            else [],
            "unset_parameters": [
                key for key in _SAMPLING_PARAMETER_KEYS if key not in request_kwargs
            ],
            "rehydration": {
                "system_prompt_id": (
                    system_prompts[0]["system_prompt_id"] if system_prompts else None
                ),
                "toolset_id": toolset_id,
            },
        }
        model = {
            "client": client_kind,
            "model": kwargs.get("model"),
            "provider": None,
            "api_base_kind": kwargs.get("api_base"),
            "reasoning_effort": context.reasoning_effort,
            "temperature": kwargs.get("temperature"),
            "top_p": kwargs.get("top_p"),
            "max_tokens": kwargs.get("max_tokens"),
            "seed": kwargs.get("seed"),
            "tool_choice": kwargs.get("tool_choice"),
        }
        prompt = {
            "messages": prompt_messages,
            "system_prompt_id": (
                system_prompts[0]["system_prompt_id"] if system_prompts else None
            ),
            "system_prompt_sha256": (
                system_prompts[0]["system_prompt_sha256"] if system_prompts else None
            ),
            "user_prompt_sha256": _hash_user_messages(prompt_messages),
            "toolset_id": toolset_id,
            "sections": _to_jsonable(context.prompt_sections or []),
            "sections_are_best_effort": True,
            "overflow": {"did_overflow": False, "dropped_sections": []},
        }
        return {
            "model": model,
            "request": request,
            "prompt": prompt,
            "system_prompts": system_prompts,
            "toolset": toolset,
        }

    def _handle_failure(self, operation: Any) -> None:
        try:
            operation()
        except Exception:
            self._capture_incomplete = True
            self._write_capture_status(capture_incomplete=True)
            if self.failure_policy == "fail":
                raise
            _logger.warning(
                "prompt dataset capture failed; continuing because "
                "PROMPT_DATASET_CAPTURE_FAILURE_POLICY=warn",
                exc_info=True,
            )

    def _write_capture_status(self, *, capture_incomplete: bool) -> None:
        self._write_json(
            self.dataset_dir / "capture_status.json",
            {
                "schema_version": SCHEMA_VERSION,
                "run_id": self.run_id,
                "capture_incomplete": capture_incomplete,
            },
        )

    @staticmethod
    def _append_jsonl(path: Path, payload: Mapping[str, Any]) -> None:
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False, sort_keys=True))
            f.write("\n")

    @staticmethod
    def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


def _to_jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {str(k): _to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_to_jsonable(v) for v in value]
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return _to_jsonable(model_dump(mode="json"))
    dict_method = getattr(value, "dict", None)
    if callable(dict_method):
        return _to_jsonable(dict_method())
    return str(value)


def _error_payload(error: BaseException) -> dict[str, Any]:
    error_code = getattr(error, "error_code", None)
    return {
        "type": type(error).__name__,
        "error_code": str(error_code) if error_code is not None else None,
        "message": _mask_secretish_text(str(error))[:1000],
    }


def _mask_api_base(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value)
    if "openrouter" in text:
        return "masked:openrouter"
    if "localhost" in text or "127.0.0.1" in text:
        return "masked:local"
    return "masked:custom"


def _mask_secretish_text(text: str) -> str:
    # 最小限の保険。Phase 1 は request key から secret を落とすのが主防御。
    for marker in ("api_key=", "Authorization:", "Bearer "):
        if marker in text:
            text = text.replace(marker, f"{marker}<masked>")
    return text


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        _to_jsonable(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _id_with_hash(prefix: str, value: Any) -> str:
    raw = value if isinstance(value, bytes) else _canonical_json_bytes(value)
    return f"{prefix}:sha256:{hashlib.sha256(raw).hexdigest()}"


def _tool_names(tools: Any) -> list[str]:
    names: list[str] = []
    if not isinstance(tools, list):
        return names
    for tool in tools:
        if not isinstance(tool, dict):
            continue
        name = tool.get("function", {}).get("name")
        if isinstance(name, str):
            names.append(name)
    return names


def _hash_user_messages(messages: list[dict[str, Any]]) -> str:
    user_messages = [m for m in messages if isinstance(m, dict) and m.get("role") == "user"]
    return hashlib.sha256(_canonical_json_bytes(user_messages)).hexdigest()


def _utc_now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


__all__ = [
    "PromptDatasetCallContext",
    "PromptDatasetCaptureSink",
    "canonicalize_request",
    "compute_request_hash",
    "new_llm_call_id",
    "reconstruct_request",
]
