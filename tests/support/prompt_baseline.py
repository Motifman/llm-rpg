"""比べる資料にするプロンプトを、シナリオから組む。

資料 (``tests/fixtures/prompts/*.json``) は、組み立てを作業記憶へ切り替える前の main で
このモジュールを走らせて書いた。``first_turn`` と ``after_repeated_waits`` は ``21a33e4c9``、
``with_memory``、``after_power_cut``、``every_scenario_sha256.json`` は ``24ec78dab`` (どちらも切り替える前)。
#1630 の 4 本目で、目的をシステムプロンプトへ移し、作法と環境の決まりを分けたあとの文に書き直した
(design_decisions D1630-4)。動かした文のほかは、書き直す前の資料と一字一句同じ。
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ai_rpg_world.application.llm.services.dynamic_argument_candidates import (
    inject_dynamic_argument_candidate_table,
)
from ai_rpg_world.application.llm.services.tool_call_loop_guard import ToolCallLoopGuardService
from ai_rpg_world.application.world_runtime.world_runtime import WorldRuntime, create_world_runtime
from ai_rpg_world.being.domain.episode import Episode, EpisodeIndex
from ai_rpg_world.being.domain.memo_book import MemoKind
from ai_rpg_world.being.domain.short_term_memory import Backstory, ShortTermMemory
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

REPO_ROOT = Path(__file__).resolve().parents[2]
BASELINE_DIR = REPO_ROOT / "tests" / "fixtures" / "prompts"
SCENARIO_DIR = REPO_ROOT / "data" / "scenarios"
BASELINE_SCENARIOS = ("mine_village_v1", "station_drill")
EVERY_SCENARIO_PATH = BASELINE_DIR / "every_scenario_sha256.json"
#: 締めの一文の 2 通り (tool_choice が required と auto) と、候補表を差し込まない評価の段の文。
PROMPT_MODES = ("required", "auto", "assess")
_REPEATED_WAITS = 3


def baseline_path(scenario_name: str) -> Path:
    return BASELINE_DIR / f"{scenario_name}.json"


def build_baseline(scenario_name: str) -> dict[str, Any]:
    """最初のターンの全員、1 人目が同じ待機を繰り返した直後、1 人目の記憶に中身があるターンを組む。

    記憶に中身があるターンは、いきさつ・目次・メモ・知っている人がそろう。station_drill では
    停電を起こし、同じ待機も繰り返すので、知らせと繰り返しの警告も出る。いきさつを入れたので、
    直近の出来事は空のまま。直近の出来事に中身があるターンは、station_drill で停電を起こした直後に組む。
    """
    baseline: dict[str, Any] = {
        "first_turn": _first_turn(scenario_name),
        "after_repeated_waits": _after_repeated_waits(scenario_name),
        "with_memory": _with_memory(scenario_name),
    }
    if scenario_name == "station_drill":
        baseline["after_power_cut"] = _after_power_cut()
    return baseline


def build_every_scenario() -> dict[str, dict[str, dict[str, str]]]:
    """data/scenarios の全シナリオの最初のターンの全員の文を、モードごとに sha256 で返す。"""
    hashes: dict[str, dict[str, dict[str, str]]] = {}
    for path in sorted(SCENARIO_DIR.glob("*.json")):
        runtime = _runtime(path.stem)
        hashes[path.stem] = {
            str(pid.value): {mode: _sha256(_prompt(runtime, pid, mode=mode)) for mode in PROMPT_MODES}
            for pid in runtime.get_player_ids()
        }
    return hashes


def _first_turn(scenario_name: str) -> dict[str, dict[str, str]]:
    runtime = _runtime(scenario_name)
    return {str(pid.value): _prompt(runtime, pid) for pid in runtime.get_player_ids()}


def _after_repeated_waits(scenario_name: str) -> dict[str, str]:
    runtime = _runtime(scenario_name)
    player_id = runtime.get_player_ids()[0]
    _repeat_waits(runtime, player_id)
    return _prompt(runtime, player_id)


def _with_memory(scenario_name: str) -> dict[str, str]:
    runtime = _runtime(scenario_name)
    player_id = runtime.get_player_ids()[0]
    _fill_memory(runtime, player_id)
    if scenario_name == "station_drill":
        _cut_power(runtime)
        _repeat_waits(runtime, player_id)
    return _prompt(runtime, player_id)


def _after_power_cut() -> dict[str, str]:
    runtime = _runtime("station_drill")
    _cut_power(runtime)
    return _prompt(runtime, runtime.get_player_ids()[0])


def _cut_power(runtime: WorldRuntime) -> None:
    control_terminal = ItemSpecId.create(runtime.id_mapper.get_int("item_spec", "control_terminal"))
    runtime.do_interact_with_item(PlayerId(3), control_terminal, "cut_power")


def _repeat_waits(runtime: WorldRuntime, player_id: PlayerId) -> None:
    guard = ToolCallLoopGuardService(
        observation_buffer=runtime._obs_buffer,
        time_label_provider=lambda: None,
        clock=lambda: datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    runtime.set_tool_call_loop_guard(guard)
    for _ in range(_REPEATED_WAITS):
        guard.record_and_check(player_id, "wait", {}, success=True, result_summary="しばらく待った。")


def _fill_memory(runtime: WorldRuntime, player_id: PlayerId) -> None:
    acting = runtime._acting_being_for(player_id)
    assert acting is not None
    being_id = acting.being_id
    environment_name = runtime.scenario.metadata.title
    runtime._being_short_term_memory_store.replace_all_by_being(
        ShortTermMemory(
            being_id,
            backstories=(
                Backstory(flow="坑道の入口を確かめた", mood="落ち着かない", written_turn=1, until_turn=1),
                Backstory(flow="仲間と分かれて調べることにした", mood="", written_turn=2, until_turn=2),
            ),
            recent_from=3,
        )
    )
    episodes = runtime._being_episode_store
    for number, summary in enumerate(("昇降機の噂を聞いた", "雪の峠を見に行った"), start=1):
        episodes.add(
            Episode.write(
                being_id=being_id,
                episode_id=f"{number:06x}00-0000-4000-8000-000000000000",
                environment_name=environment_name,
                written_turn=number,
                index=EpisodeIndex(summary=summary, recall_when="外へ出る道の話が出たとき"),
                body=f"{summary}ときの本文。",
                taken_handles={e.handle for e in episodes.list_by_being(being_id)},
            )
        )
    book = runtime._being_memo_store.get(being_id)
    book.add(
        memo_id="00000001-0000-4000-8000-000000000000",
        kind=MemoKind.TODO,
        text="カンテラの油を確かめる",
        provenance=None,
        turn=2,
        environment_name=environment_name,
    )
    runtime._being_memo_store.save(book)


def _runtime(scenario_name: str) -> WorldRuntime:
    return create_world_runtime(SCENARIO_DIR / f"{scenario_name}.json")


def _prompt(runtime: WorldRuntime, player_id: PlayerId, *, mode: str = "required") -> dict[str, str]:
    tool_names = {d.name for d in runtime.get_tool_definitions(player_id=player_id)}
    instruction = runtime.escape_game_action_instruction(sorted(tool_names)) if mode == "auto" else None
    prompt = runtime.build_full_prompt(player_id, action_instruction=instruction)
    if mode != "assess":
        prompt = inject_dynamic_argument_candidate_table(prompt, tool_names)
    system, user = (m["content"] for m in prompt["messages"])
    return {"system": system, "user": user}


def _sha256(prompt: dict[str, str]) -> str:
    return hashlib.sha256(json.dumps(prompt, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


if __name__ == "__main__":
    logging.disable(logging.CRITICAL)
    for name in BASELINE_SCENARIOS:
        text = json.dumps(build_baseline(name), ensure_ascii=False, indent=2) + "\n"
        baseline_path(name).write_text(text, encoding="utf-8")
    EVERY_SCENARIO_PATH.write_text(
        json.dumps(build_every_scenario(), ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8"
    )
