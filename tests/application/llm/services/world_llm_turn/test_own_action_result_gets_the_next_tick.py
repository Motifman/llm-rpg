"""成功した自分の行動のあとは次の tick に手番が回り、休むのは wait を選んだときと移動中だけであることを保証する (Issue #1597)。

`var/runs/mine_v1_005` では、記憶の呼び出し、何も見つからなかった探索、紙切れを
読むだけの interact が成功したあと、本人を起こす観測が出ず、待ち時間のタイマーが
切れるまで 6 tick 手番が回らなかった。

本番と同じ session (待ち時間のタイマー・観測による起こし合い・到着の知らせを
すべて配線したもの) を組み、world tick を進めて手番の tick を trace から読む。
"""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import pytest
from tests.support.trace_recorders import CollectingTraceRecorder

from ai_rpg_world.application.llm.services.world_llm_turn.turn_trigger import (
    FOLLOW_UP_REASON_REST_CHOSEN,
    FOLLOW_UP_REASON_SUCCEEDED,
    FOLLOW_UP_REASON_TRAVELING,
)
from ai_rpg_world.application.llm.tool_constants import TOOL_NAME_EPISODE_RECALL
from ai_rpg_world.application.llm.wiring.resolved_runtime_config import (
    ResolvedLlmRuntimeConfig,
)
from ai_rpg_world.application.trace.events import TraceEventKind
from ai_rpg_world.being.domain.episode import Episode, EpisodeIndex
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.presentation.spot_graph_game.runtime_manager import GameRuntimeManager
from ai_rpg_world.presentation.spot_graph_game.schemas import (
    CharacterCreateRequest,
    SessionCreateRequest,
)

_SCENARIO = (
    Path(__file__).resolve().parents[5] / "data" / "scenarios" / "mine_village_v1.json"
)
_HAL = PlayerId(1)
_WAIT = {"name": "wait", "arguments": {"inner_thought": "様子を見る"}}
_EXPLORE = {"name": "explore", "arguments": {"inner_thought": "手がかりを探す"}}
_SEARCH_DRAWER = {
    "name": "interact",
    "arguments": {
        "target_label": "事務机",
        "action_name": "search_desk_drawer",
        "inner_thought": "引き出しに何かあるかもしれない",
    },
}
_MEMO_LIST = {"name": "memo_list", "arguments": {}}
_TRAVEL_TWO_TICKS = {
    "name": "travel_to",
    "arguments": {"destination_label": "雪の峠道", "inner_thought": "峠を見に行く"},
}


@pytest.fixture(autouse=True)
def _without_developer_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("OPENROUTER_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(name, raising=False)


class _HalScriptedClient:
    """ハルには台本の順に行動を返し、台本が尽きたら wait を返す。ほかの人は常に wait。"""

    def __init__(self, script: list[dict[str, Any]]) -> None:
        self._script = list(script)

    def invoke(self, messages: Any, tools: Any, tool_choice: str = "required", **kwargs: Any):
        if "あなたはハル" in messages[0]["content"] and self._script:
            return self._script.pop(0)
        return _WAIT


class _Session:
    def __init__(self, wiring: Any, recorder: CollectingTraceRecorder) -> None:
        self.wiring = wiring
        self.runtime = wiring.runtime
        self.recorder = recorder

    def place_hal(self, spot: str) -> None:
        graph = self.runtime._spot_graph_repo.find_graph()
        entity = EntityId.create(int(_HAL))
        graph.unplace_entity(entity)
        graph.place_entity(
            entity, SpotId.create(self.runtime.id_mapper.get_int("spot", spot))
        )
        self.runtime._spot_graph_repo.save(graph)

    def script_hal(self, script: list[dict[str, Any]]) -> None:
        self.wiring.llm_client = _HalScriptedClient(script)

    def advance(self, ticks: int) -> None:
        for _ in range(ticks):
            self.runtime.advance_tick()

    def hal_turns(self) -> list[tuple[int, str]]:
        return [
            (e.tick, e.payload["tool"])
            for e in self.recorder.of_kind("action_result")
            if e.player_id == int(_HAL)
        ]

    def hal_results(self) -> list[bool]:
        return [
            e.payload["success"]
            for e in self.recorder.of_kind("action_result")
            if e.player_id == int(_HAL)
        ]

    def hal_follow_ups(self) -> list[dict[str, Any]]:
        return [
            {"tick": e.tick, **e.payload}
            for e in self.recorder.of_kind(TraceEventKind.OWN_ACTION_FOLLOW_UP)
            if e.player_id == int(_HAL)
        ]

    def idle_timeout_ticks(self) -> int:
        return int(self.runtime._runtime_config.llm_idle_timeout_ticks)


def _open_session(tmp: str, config: ResolvedLlmRuntimeConfig | None = None) -> _Session:
    manager = GameRuntimeManager(
        scenarios_dir=_SCENARIO.parent,
        characters_path=Path(tmp) / "characters.json",
        runtime_config=config or ResolvedLlmRuntimeConfig.for_tests(),
    )
    character = manager.create_character(CharacterCreateRequest(name="probe"))
    summary = manager.create_session(
        SessionCreateRequest(world_id=_SCENARIO.stem, character_ids=[character.id])
    )
    wiring = manager._sessions[summary.session_id].llm_wiring
    recorder = CollectingTraceRecorder()
    wiring.runtime.set_trace_recorder(recorder)
    return _Session(wiring, recorder)


def _episode_config() -> ResolvedLlmRuntimeConfig:
    return ResolvedLlmRuntimeConfig.from_mapping(
        values={
            "SHORT_TERM_MEMORY_KIND": "rolling_summary",
            "BEING_EPISODE_WRITING_ENABLED": "1",
            "BEING_EPISODE_INDEX_ORDER": "recalled_rises_to_top",
            "TYPED_JUDGMENT_PROVIDER": "stub",
        }
    )


def _write_hal_episode(session: _Session) -> Episode:
    runtime = session.runtime
    runtime._acting_being_for(_HAL)
    being_id = runtime.aux_being_resolver.resolve_being_id(
        runtime.aux_being_default_world_id, _HAL
    )
    store = runtime._being_episode_store
    episode = Episode.write(
        episode_id="00000100-0000-4000-8000-000000000000",
        environment_name=runtime.scenario.metadata.title,
        written_turn=0,
        index=EpisodeIndex(summary="峠道が雪で閉ざされた", recall_when="外へ出る道の話が出たとき"),
        body="峠道が雪で閉ざされたときの本文。",
        taken_handles={e.handle for e in store.list_by_being(being_id)},
    )
    store.add(being_id, episode)
    return episode


def _gaps(turns: list[tuple[int, str]]) -> list[int]:
    return [later[0] - earlier[0] for earlier, later in zip(turns, turns[1:])]


class TestSucceededActionWithoutObservationGetsTheNextTick:
    """mine_v1_005 で 6 tick 空いた成功の形のあと、ほかに起こす観測が無くても次の tick に手番が回ることを保証する。"""

    @pytest.mark.parametrize(
        ("spot", "action", "tool"),
        [
            ("north_shaft_head", _EXPLORE, "explore"),
            ("company_office", _SEARCH_DRAWER, "interact"),
            ("north_shaft_head", _MEMO_LIST, "memo_list"),
        ],
        ids=["explore_finds_nothing", "interact_reads_a_note", "memo_tool"],
    )
    def test_next_turn_comes_on_the_next_tick(
        self, spot: str, action: dict[str, Any], tool: str
    ) -> None:
        """何も見つからない探索・紙切れを読むだけの interact・メモのツールが成功すると、本人の次の手番は 1 tick 後に来る。"""
        with TemporaryDirectory() as tmp:
            session = _open_session(tmp)
            session.place_hal(spot)
            session.script_hal([action])

            session.advance(session.idle_timeout_ticks() + 3)

            turns = session.hal_turns()
            assert turns[0][1] == tool
            assert _gaps(turns)[0] == 1

    def test_episode_recall_gets_the_next_tick(self) -> None:
        """記憶の呼び出し (episode_recall) が成功すると、思い出した内容で次の手を決められるよう、本人の次の手番は 1 tick 後に来る。"""
        with TemporaryDirectory() as tmp:
            session = _open_session(tmp, _episode_config())
            episode = _write_hal_episode(session)
            session.script_hal(
                [{"name": TOOL_NAME_EPISODE_RECALL, "arguments": {"handles": [episode.handle]}}]
            )

            session.advance(session.idle_timeout_ticks() + 3)

            turns = session.hal_turns()
            assert turns[0][1] == TOOL_NAME_EPISODE_RECALL
            assert session.hal_results()[0] is True
            assert _gaps(turns)[0] == 1

    def test_the_recorded_follow_up_says_why(self) -> None:
        """次の tick に回した手番は、trace の own_action_follow_up に rescheduled=True と、成功したことを理由として残る。"""
        with TemporaryDirectory() as tmp:
            session = _open_session(tmp)
            session.script_hal([_EXPLORE])

            session.advance(session.idle_timeout_ticks() + 1)

            first_turn_tick = session.hal_turns()[0][0]
            assert session.hal_follow_ups()[0] == {
                "tick": first_turn_tick,
                "rescheduled": True,
                "reason": FOLLOW_UP_REASON_SUCCEEDED,
            }


class TestWaitRestsUntilWoken:
    """wait を選んだときだけは、今までどおり起こされるまで手番が回らないことを保証する。"""

    @pytest.mark.parametrize(
        "inner_thought", ["様子を見る", ""], ids=["with_thought", "empty_thought"]
    )
    def test_wait_sleeps_until_the_idle_timer(self, inner_thought: str) -> None:
        """wait のあと、ほかに起こす観測が無ければ、次の手番は待ち時間のタイマーが切れる tick まで来ない。心の声が空で結果の文に警告が付く wait でも同じ。"""
        with TemporaryDirectory() as tmp:
            session = _open_session(tmp)
            session.script_hal([{"name": "wait", "arguments": {"inner_thought": inner_thought}}])

            session.advance(2 * session.idle_timeout_ticks() + 2)

            turns = session.hal_turns()
            assert _gaps(turns)[0] == session.idle_timeout_ticks()

    def test_wait_is_recorded_as_not_rescheduled(self) -> None:
        """wait の手番は、trace の own_action_follow_up に rescheduled=False と、休むことを選んだ理由で残る。"""
        with TemporaryDirectory() as tmp:
            session = _open_session(tmp)
            session.script_hal([_WAIT])

            session.advance(session.idle_timeout_ticks() + 1)

            assert session.hal_follow_ups()[0]["rescheduled"] is False
            assert session.hal_follow_ups()[0]["reason"] == FOLLOW_UP_REASON_REST_CHOSEN


class TestTravelingDoesNotGetTurns:
    """時間のかかる移動を始めたあとは、着くまで手番が回らず、着いた tick に回ることを保証する。"""

    def test_two_tick_travel_gets_its_next_turn_on_arrival(self) -> None:
        """2 tick かかる道へ移動を始めると、途中の 1 tick 後には手番が来ず、着いた 2 tick 後に来る。"""
        with TemporaryDirectory() as tmp:
            session = _open_session(tmp)
            session.script_hal([_TRAVEL_TWO_TICKS])

            session.advance(session.idle_timeout_ticks() + 4)

            turns = session.hal_turns()
            assert turns[0][1] == "travel_to"
            assert _gaps(turns)[0] == 2

    def test_travel_is_recorded_as_not_rescheduled(self) -> None:
        """移動を始めた手番は、trace の own_action_follow_up に rescheduled=False と、移動中である理由で残る。"""
        with TemporaryDirectory() as tmp:
            session = _open_session(tmp)
            session.script_hal([_TRAVEL_TWO_TICKS])

            session.advance(session.idle_timeout_ticks() + 1)

            assert session.hal_follow_ups()[0]["rescheduled"] is False
            assert session.hal_follow_ups()[0]["reason"] == FOLLOW_UP_REASON_TRAVELING


class TestRepeatingTheSameActionIsWarned:
    """毎 tick 手番が回るようになっても、同じ行動の繰り返しには今ある繰り返しの警告が効くことを保証する。"""

    def test_exploring_the_same_place_every_tick_raises_a_loop_warning(self) -> None:
        """何も見つからない探索を 5 回続けると、5 回目の tick にループ警告が 1 件出る。探索の連続回数の閾値は 5。"""
        with TemporaryDirectory() as tmp:
            session = _open_session(tmp)
            session.script_hal([_EXPLORE] * 5)

            session.advance(session.idle_timeout_ticks() + 6)

            explores = [tick for tick, tool in session.hal_turns() if tool == "explore"]
            warnings = [
                e.tick
                for e in session.recorder.of_kind(TraceEventKind.LOOP_GUARD_WARNING)
                if e.player_id == int(_HAL)
            ]
            assert _gaps([(t, "") for t in explores]) == [1, 1, 1, 1]
            assert warnings == [explores[-1]]



class _GateThatDropsEveryoneAfterTheFirstWave:
    """1 回目の wave は全員を通し、2 回目からは問われた全員を回さない起動判定。問われた人を覚える。"""

    def __init__(self) -> None:
        self.waves = 0
        self.asked: list[set[int]] = []

    def candidates(self, scheduled: list[PlayerId]) -> list[PlayerId]:
        return list(scheduled)

    def decide_wave(
        self, player_ids: list[PlayerId], *, scheduled: list[PlayerId] | None = None
    ) -> list[PlayerId]:
        self.waves += 1
        self.asked.append({int(p.value) for p in player_ids})
        return list(player_ids) if self.waves == 1 else []


class TestFollowUpIsNotJudgedByTheTurnGate:
    """起動判定は未読の観測で動く必要があるかを問うもので、自分の行動の結果を材料に持たないため、自分の行動のあとに回した手番を判定にかけないことを保証する。"""

    def test_follow_up_runs_even_when_the_gate_drops_everyone(self) -> None:
        """探索が成功した次の wave で、起動判定が問われた全員を回さないとしても、ハルは判定にかけられずに手番が回る。"""
        with TemporaryDirectory() as tmp:
            session = _open_session(tmp)
            gate = _GateThatDropsEveryoneAfterTheFirstWave()
            session.wiring.turn_gate = gate
            session.script_hal([_EXPLORE])
            trigger = session.wiring.llm_turn_trigger
            trigger.schedule_turn(_HAL)

            trigger.run_scheduled_turns()
            trigger.run_scheduled_turns()

            assert [tool for _, tool in session.hal_turns()] == ["explore", "wait"]
            assert all(int(_HAL) not in asked for asked in gate.asked[1:])

    def test_observation_woken_player_is_still_judged(self) -> None:
        """正の対照: 同じ wave で観測により pending に入ったミオは起動判定にかけられ、回さないと判定されれば手番が来ない。"""
        with TemporaryDirectory() as tmp:
            session = _open_session(tmp)
            gate = _GateThatDropsEveryoneAfterTheFirstWave()
            session.wiring.turn_gate = gate
            session.script_hal([_EXPLORE])
            trigger = session.wiring.llm_turn_trigger
            mio = PlayerId(2)
            trigger.schedule_turn(_HAL)
            trigger.run_scheduled_turns()

            trigger.schedule_turn(mio)
            trigger.run_scheduled_turns()

            assert gate.asked[1] == {int(mio)}
            mio_turns = [
                e for e in session.recorder.of_kind("action_result") if e.player_id == int(mio)
            ]
            assert mio_turns == []
