"""Prompt dataset capture と LLM session ID ヘルパ。"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ai_rpg_world.application.llm.services.world_llm_turn.wiring import (
        WorldLlmWiring,
    )

import hashlib
import logging
from collections.abc import Mapping
from types import SimpleNamespace
from typing import Any

from ai_rpg_world.application.llm.contracts.dtos import LlmCommandResultDto
from ai_rpg_world.application.llm.services.dynamic_argument_candidates import (
    build_dynamic_argument_candidate_snapshot,
)
from ai_rpg_world.application.llm.services.prompt_dataset_capture import (
    PromptDatasetCallContext,
    new_llm_call_id,
)
from ai_rpg_world.application.llm.services.world_llm_turn.types import LlmPhaseAResult
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

logger = logging.getLogger(__name__)


def _prompt_tool_names(prompt: dict[str, Any]) -> set[str]:
    """prompt builder が返す定義形式と OpenAI payload 形式の双方から名前を読む。"""
    names: set[str] = set()
    for definition in prompt.get("tools", []):
        if isinstance(definition, Mapping):
            function = definition.get("function")
            raw = function.get("name") if isinstance(function, Mapping) else definition.get("name")
        else:
            raw = getattr(definition, "name", "")
        name = str(raw or "").strip()
        if name:
            names.add(name)
    return names


def build_prompt_capture_context(
    wiring: WorldLlmWiring,
    *,
    player_id: PlayerId,
    prompt: dict[str, Any],
    tool_choice: Any,
    reasoning_effort: str | None,
    attempt_index: int,
    parent_attempt_id: str | None,
    phase: str = "one_step",
    exposed_tool_names: set[str] | None = None,
) -> Any | None:
    """prompt dataset 有効時に 1 LLM 呼び出しの保存文脈を作る。"""

    sink = wiring.prompt_dataset_sink
    if sink is None:
        return None
    being_id = resolve_prompt_capture_being_id(wiring, player_id)
    character_name = resolve_prompt_capture_character_name(wiring, player_id)
    persona_snapshot = str(prompt.get("persona_snapshot") or "")
    persona_source = persona_snapshot or character_name
    persona_id = "persona:sha256:" + hashlib.sha256(persona_source.encode("utf-8")).hexdigest()
    world_tick: int | None
    try:
        world_tick = int(wiring.runtime.current_tick())
    except Exception:
        world_tick = None
    context = PromptDatasetCallContext(
        llm_call_id=new_llm_call_id(),
        run_id=sink.run_id,
        world_id=resolve_prompt_capture_world_id(wiring),
        being_id=being_id,
        player_id=int(player_id.value),
        persona_id=persona_id,
        character_name=character_name,
        turn_index=world_tick or 0,
        attempt_index=attempt_index,
        parent_attempt_id=parent_attempt_id,
        world_tick=world_tick,
        phase=phase,
        time_of_day={"label": time_label(wiring)},
        provenance=getattr(sink, "_run_metadata", {}),
        reasoning_effort=reasoning_effort,
        prompt_sections=[],
        dynamic_argument_candidates=build_dynamic_argument_candidate_snapshot(
            prompt["tool_runtime_context"],
            exposed_tool_names or _prompt_tool_names(prompt),
        ),
    )
    return SimpleNamespace(sink=sink, context=context)


def llm_session_id(wiring: WorldLlmWiring, player_id: PlayerId) -> str:
    """同じ run・世界・player の LLM 呼び出しへ安定した会話 ID を返す。"""

    raw = f"{wiring.llm_session_run_id}:w{wiring.llm_session_world_id}:p{player_id.value}"
    if len(raw) <= 256:
        return raw
    return "llm-rpg:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def llm_session_kwargs(wiring: WorldLlmWiring, player_id: PlayerId) -> dict[str, str]:
    """配信先固定を使うときだけ session_id の送信値を組み立てる。

    無効時は空文字や ``None`` を渡さず、キーワード自体を省く。これにより
    OpenRouter 用の値検査へ入らず、prompt dataset にも実送信どおりキー無しで残る。
    """

    config = getattr(wiring.runtime, "_runtime_config", None)
    if not bool(getattr(config, "llm_session_id_enabled", True)):
        return {}
    return {"session_id": llm_session_id(wiring, player_id)}


def resolve_prompt_capture_being_id(wiring: WorldLlmWiring, player_id: PlayerId) -> str:
    resolver = getattr(wiring.runtime, "aux_being_resolver", None)
    world_id = getattr(wiring.runtime, "aux_being_default_world_id", None)
    if resolver is None or world_id is None:
        raise RuntimeError("PROMPT_DATASET_CAPTURE_ENABLED requires aux Being resolver")
    being_id = resolver.resolve_being_id(world_id, player_id)
    if being_id is None:
        raise RuntimeError(f"PROMPT_DATASET_CAPTURE_ENABLED requires being_id for player_id={player_id.value}")
    return str(being_id.value)


def resolve_prompt_capture_world_id(wiring: WorldLlmWiring) -> int | None:
    world_id = getattr(wiring.runtime, "aux_being_default_world_id", None)
    value = getattr(world_id, "value", None)
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def resolve_prompt_capture_character_name(wiring: WorldLlmWiring, player_id: PlayerId) -> str:
    for spawn in getattr(getattr(wiring.runtime, "scenario", None), "player_spawns", []):
        try:
            if int(spawn.player_id) == int(player_id.value):
                return str(getattr(spawn, "name", f"player_{player_id.value}"))
        except Exception:
            continue
    return f"player_{player_id.value}"


def record_prompt_dataset_turn_result(
    wiring: WorldLlmWiring,
    phase_a: LlmPhaseAResult,
    result: LlmCommandResultDto,
) -> None:
    sink = wiring.prompt_dataset_sink
    if sink is None or phase_a.llm_call_id is None:
        return
    try:
        world_tick = int(wiring.runtime.current_tick())
    except Exception:
        world_tick = None
    turn_result = {
        "action_success": bool(result.success),
        "action_result_error_code": result.error_code,
        "result_summary": result.message,
        "remediation": result.remediation,
        "was_no_op": bool(result.was_no_op),
    }
    technical_error_detail = (result.trace_payload or {}).get("technical_error_detail")
    if technical_error_detail is not None:
        turn_result["technical_error_detail"] = technical_error_detail
    sink.record_turn_result(
        llm_call_id=phase_a.llm_call_id,
        run_id=sink.run_id,
        world_tick=world_tick,
        player_id=int(phase_a.player_id.value),
        result=turn_result,
    )


def time_label(wiring: WorldLlmWiring) -> str:
    return wiring._time_label()
