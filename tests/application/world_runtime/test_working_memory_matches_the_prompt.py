"""作業記憶 (#1630) から組んだ文が、今の組み立てのプロンプトと一字一句同じになることを保証する (design_decisions D1630-2)。

同じ試験の中で、今の組み立て (``build_full_prompt`` と候補表の差し込み) と作業記憶の組み立てを
両方動かして比べる。区画に中身があるターン (知っている人、いきさつ、直近の出来事、目次、メモ、知らせ)
も比べる。
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

import pytest

from ai_rpg_world.application.llm.services.dynamic_argument_candidates import inject_dynamic_argument_candidate_table
from ai_rpg_world.application.llm.services.tool_call_loop_guard import ToolCallLoopGuardService
from ai_rpg_world.application.world_runtime.world_runtime import WorldRuntime, create_world_runtime
from ai_rpg_world.being.application.working_memory_text import message_text, system_prompt_text
from ai_rpg_world.being.domain.episode import Episode, EpisodeIndex
from ai_rpg_world.being.domain.memo_book import MemoKind
from ai_rpg_world.being.domain.short_term_memory import Backstory, ShortTermMemory
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

_SCENARIOS = Path(__file__).resolve().parents[3] / "data" / "scenarios"


@pytest.fixture(autouse=True)
def _quiet(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.CRITICAL)


def _runtime(name: str) -> WorldRuntime:
    return create_world_runtime(_SCENARIOS / f"{name}.json")


def _both(
    runtime: WorldRuntime, player_id: PlayerId, *, closing: str = "required", with_table: bool = True
) -> tuple[tuple[str, str], tuple[str, str]]:
    """(今の組み立ての system とユーザー文, 作業記憶から組んだ system とメッセージ) を返す。

    ``closing="auto"`` は tool_choice=auto のときの締めの一文で組む。``with_table=False`` は
    reason_first の評価の段のように、候補表を差し込まずに送る文を組む。
    """
    tool_names = {d.name for d in runtime.get_tool_definitions(player_id=player_id)}
    instruction = runtime.escape_game_action_instruction(sorted(tool_names)) if closing == "auto" else None
    prompt = runtime.build_full_prompt(player_id, action_instruction=instruction)
    if with_table:
        prompt = inject_dynamic_argument_candidate_table(prompt, tool_names)
    memory = runtime.working_memory_for(player_id, prompt)
    system, user = (m["content"] for m in prompt["messages"])
    return (system, user), (system_prompt_text(memory), message_text(memory))


def _being_of(runtime: WorldRuntime, player_id: PlayerId):
    acting = runtime._acting_being_for(player_id)
    assert acting is not None
    return acting.being_id


def _fill_memory(runtime: WorldRuntime, player_id: PlayerId) -> None:
    """いきさつ、目次、メモに中身を入れる。知っている人は入るときの紹介で入っている。"""
    being_id = _being_of(runtime, player_id)
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
    for number, summary in enumerate(("昇降機の噂を聞いた", "雪の峠を見に行った"), start=1):
        episodes = runtime._being_episode_store
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


def _repeat_waits(runtime: WorldRuntime, player_id: PlayerId) -> None:
    guard = ToolCallLoopGuardService(
        observation_buffer=runtime._obs_buffer,
        time_label_provider=lambda: None,
        clock=lambda: datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    runtime.set_tool_call_loop_guard(guard)
    for _ in range(3):
        guard.record_and_check(player_id, "wait", {}, success=True, result_summary="しばらく待った。")


@pytest.mark.parametrize("scenario", ["mine_village_v1", "station_drill"])
class TestSameText:
    """廃坑の山村と station_drill で、作業記憶から組んだ文が今のプロンプトと一字一句同じになることを保証する。"""

    def test_first_turn_of_everyone(self, scenario: str) -> None:
        """最初のターンの全員で、system とユーザー文が同じになる。"""
        runtime = _runtime(scenario)

        for player_id in runtime.get_player_ids():
            current, composed = _both(runtime, player_id)
            assert composed == current, player_id

    def test_turn_after_repeating_the_same_wait(self, scenario: str) -> None:
        """同じ待機を 3 回続けた直後 (繰り返しの警告が出る) で、同じになる。"""
        runtime = _runtime(scenario)
        player_id = runtime.get_player_ids()[0]
        _repeat_waits(runtime, player_id)

        current, composed = _both(runtime, player_id)

        assert "⚠" in current[1]
        assert composed == current

    def test_turn_with_backstory_index_and_memo(self, scenario: str) -> None:
        """いきさつ、目次、メモ、知っている人がそろったターンで、同じになる。"""
        runtime = _runtime(scenario)
        player_id = runtime.get_player_ids()[0]
        _fill_memory(runtime, player_id)

        current, composed = _both(runtime, player_id)

        assert all(
            text in current[1]
            for text in ("[最新]", "【知っている人】", "昇降機の噂を聞いた", "カンテラの油を確かめる")
        )
        assert composed == current


_EVERY_SCENARIO = sorted(path.stem for path in _SCENARIOS.glob("*.json"))


@pytest.mark.parametrize("scenario", _EVERY_SCENARIO)
@pytest.mark.parametrize(("closing", "with_table"), [("required", True), ("auto", True), ("required", False)])
def test_first_turn_of_every_scenario(scenario: str, closing: str, with_table: bool) -> None:
    """data/scenarios の全シナリオの最初のターンの全員で、締めの一文の 2 通りと、候補表を差し込まない評価の段の文が同じになる。"""
    runtime = _runtime(scenario)

    for player_id in runtime.get_player_ids():
        current, composed = _both(runtime, player_id, closing=closing, with_table=with_table)
        assert composed == current, player_id


def test_turn_with_an_ongoing_condition_and_events() -> None:
    """station_drill で停電が起き、知らせと直近の出来事に中身があるターンで、同じになる。"""
    runtime = _runtime("station_drill")
    control_terminal = ItemSpecId.create(runtime.id_mapper.get_int("item_spec", "control_terminal"))
    runtime.do_interact_with_item(PlayerId(3), control_terminal, "cut_power")
    _repeat_waits(runtime, PlayerId(1))

    current, composed = _both(runtime, PlayerId(1))

    assert all(text in current[1] for text in ("【進行中の異常】", "⚠", "集会室の雰囲気が変わった"))
    assert composed == current
