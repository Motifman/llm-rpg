"""断られた行動に添えた発言も、成功した行動と同じ範囲に届くことを保証する (#1601)。

`var/runs/mine_v1_006` の T17〜T20 で、籠の前の駆け引きの宣言 (「サヨ、鍵を差せ」
「俺もハルと二人で外へ出る約束なんだ」) が、どれも前提条件で断られた interact に
添えられていて、相手に届いていなかった。発言は各ツールの成功の経路の最後でだけ
出ていたので、断られると発言の行を通らなかった。本人には何も伝わらず、聞こえた
前提で次の行動を選んでいた。

発言は dispatch で handler が返った後に出す。断られ方 (前提条件、名前の解決、疲労)
を問わない。届き方は `speak` が決めるので、試験は成功した行動と同じ観測になるかを
比べる。本番と同じ session を組み、`run_phase_b` から試す。
"""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from unittest.mock import MagicMock

import pytest

from ai_rpg_world.application.llm.services.tool_catalog.spot_graph import (
    get_spot_graph_specs,
)
from ai_rpg_world.application.llm.services.world_llm_turn.types import LlmPhaseAResult
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_SPOT_GRAPH_INTERACT,
    TOOL_NAME_SPOT_GRAPH_TEND_TO_PLAYER,
    TOOL_NAME_SPOT_GRAPH_TRAVEL_TO,
    TOOL_NAME_SPOT_GRAPH_WAIT,
)
from ai_rpg_world.application.llm.wiring.resolved_runtime_config import (
    ResolvedLlmRuntimeConfig,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.presentation.spot_graph_game.runtime_manager import GameRuntimeManager
from ai_rpg_world.presentation.spot_graph_game.schemas import (
    CharacterCreateRequest,
    SessionCreateRequest,
)

_SCENARIO = Path(__file__).resolve().parents[2] / "data" / "scenarios" / "mine_village_v1.json"
_HAL, _MIO, _GEN = PlayerId(1), PlayerId(2), PlayerId(3)
_WORDS = "ミオ、俺はお前と二人で外へ出る。誰か一人詰めて、俺たちを乗せてくれ。"
_NOT_DELIVERED = "添えた発言は届かなかった"


@pytest.fixture(autouse=True)
def _without_developer_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("OPENROUTER_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(name, raising=False)


def _session(tmp: str):
    """ハルとミオは事務所、ゲンは隣の井戸にいる session を組む。"""
    manager = GameRuntimeManager(
        scenarios_dir=_SCENARIO.parent,
        characters_path=Path(tmp) / "characters.json",
        runtime_config=ResolvedLlmRuntimeConfig.for_tests(),
    )
    character = manager.create_character(CharacterCreateRequest(name="probe"))
    summary = manager.create_session(
        SessionCreateRequest(world_id=_SCENARIO.stem, character_ids=[character.id])
    )
    wiring = manager._sessions[summary.session_id].llm_wiring
    _place(wiring.runtime, _HAL, "company_office")
    _place(wiring.runtime, _MIO, "company_office")
    _place(wiring.runtime, _GEN, "well")
    return wiring


def _place(runtime, player_id: PlayerId, spot: str) -> None:
    graph = runtime._spot_graph_repo.find_graph()
    entity = EntityId.create(int(player_id))
    graph.unplace_entity(entity)
    graph.place_entity(entity, SpotId.create(runtime.id_mapper.get_int("spot", spot)))
    runtime._spot_graph_repo.save(graph)


def _act(wiring, tool_name: str, arguments: dict[str, Any]):
    return wiring.run_phase_b(
        LlmPhaseAResult(
            player_id=_HAL,
            prompt=wiring.runtime.build_full_prompt(_HAL),
            tools_payload=[],
            tool_call={"name": tool_name, "arguments": arguments},
            exception=None,
        )
    )


def _try_the_safe_with_a_wrong_code(wiring, said: str = _WORDS):
    return _act(
        wiring,
        TOOL_NAME_SPOT_GRAPH_INTERACT,
        {
            "target_label": "金庫",
            "action_name": "open_safe",
            "parameters": {"code": "0000"},
            "say_inline": said,
            "inner_thought": "番号はこれのはずだ。",
        },
    )


def _wait_saying(wiring, said: str = _WORDS):
    return _act(
        wiring,
        TOOL_NAME_SPOT_GRAPH_WAIT,
        {"reason": "様子を見る", "say_inline": said, "inner_thought": "少し待つ。"},
    )


def _heard(wiring, player_id: PlayerId) -> list[str]:
    """聞き手の観測のうち、ハルの発言を運ぶものだけを返す。"""
    observations = wiring.runtime._obs_buffer.get_observations(player_id)
    return [e.output.prose for e in observations if _WORDS[:10] in e.output.prose]


class TestWordsWithARefusedActionAreHeard:
    """断られた行動に添えた発言が、聞こえる範囲の人に届くことを保証する。"""

    def test_words_with_an_interaction_refused_by_its_precondition_reach_the_same_spot(self) -> None:
        """金庫に違う番号を入れて前提条件で断られても、添えた発言は同じ場所のミオに全文で届く。"""
        with TemporaryDirectory() as tmp:
            wiring = _session(tmp)

            result = _try_the_safe_with_a_wrong_code(wiring)

            assert result.success is False
            assert result.error_code == "INTERACTION_PRECONDITION_FAILED"
            assert any(f"「{_WORDS}」" in prose for prose in _heard(wiring, _MIO))

    def test_words_with_an_unresolvable_target_reach_the_same_spot(self) -> None:
        """その場に無い対象を名指しして名前の解決で断られても、添えた発言は同じ場所のミオに届く。"""
        with TemporaryDirectory() as tmp:
            wiring = _session(tmp)

            result = _act(
                wiring,
                TOOL_NAME_SPOT_GRAPH_INTERACT,
                {
                    "target_label": "昇降機",
                    "action_name": "start_lift",
                    "say_inline": _WORDS,
                    "inner_thought": "籠を動かす。",
                },
            )

            assert result.success is False
            assert result.error_code == "INVALID_TARGET_LABEL"
            assert any(f"「{_WORDS}」" in prose for prose in _heard(wiring, _MIO))

    def test_words_with_a_move_refused_for_exhaustion_reach_the_same_spot(self) -> None:
        """疲労が限界で移動を断られても、添えた発言は同じ場所のミオに届く。"""
        with TemporaryDirectory() as tmp:
            wiring = _session(tmp)
            statuses = wiring.runtime._player_status_repo
            status = statuses.find_by_id(_HAL)
            status.apply_fatigue(100)
            statuses.save(status)

            result = _act(
                wiring,
                TOOL_NAME_SPOT_GRAPH_TRAVEL_TO,
                {
                    "destination_label": "井戸",
                    "say_inline": _WORDS,
                    "inner_thought": "井戸へ行く。",
                },
            )

            assert result.error_code == "EXHAUSTED"
            assert any(f"「{_WORDS}」" in prose for prose in _heard(wiring, _MIO))

    def test_words_with_a_refused_tending_reach_the_same_spot(self) -> None:
        """倒れていないミオを介抱しようとして断られても、添えた発言はミオに届く。"""
        with TemporaryDirectory() as tmp:
            wiring = _session(tmp)

            result = _act(
                wiring,
                TOOL_NAME_SPOT_GRAPH_TEND_TO_PLAYER,
                {
                    "target_player_label": "ミオ",
                    "say_inline": _WORDS,
                    "inner_thought": "ミオを起こす。",
                },
            )

            assert result.success is False
            assert any(f"「{_WORDS}」" in prose for prose in _heard(wiring, _MIO))


class TestWordsWithARefusedActionFollowTheSameRules:
    """断られた行動に添えた発言の届き方が、成功した行動の発言と同じ規則に従うことを保証する。"""

    def test_listeners_hear_a_refused_action_the_same_way_as_a_successful_one(self) -> None:
        """同じ発言を、断られた interact と成功した wait に添えると、同じ場所のミオと隣の井戸のゲンが受け取る観測は同じになる。"""
        with TemporaryDirectory() as refused_tmp, TemporaryDirectory() as succeeded_tmp:
            refused = _session(refused_tmp)
            succeeded = _session(succeeded_tmp)

            assert _try_the_safe_with_a_wrong_code(refused).success is False
            assert _wait_saying(succeeded).success is True

            for listener in (_MIO, _GEN):
                assert _heard(refused, listener) == _heard(succeeded, listener)
            assert len(_heard(succeeded, _GEN)) == 1
            assert _WORDS not in _heard(succeeded, _GEN)[0]

    def test_words_with_a_successful_action_are_heard_once(self) -> None:
        """成功した行動に添えた発言は、ミオに 1 回だけ届く (発言を出す場所を移しても二重に出ない)。"""
        with TemporaryDirectory() as tmp:
            wiring = _session(tmp)

            _wait_saying(wiring)

            assert len(_heard(wiring, _MIO)) == 1


class TestTheActorLearnsWhenTheWordsWereNotHeard:
    """発言が出せなかったとき、本人の行動の記録にそう出ることを保証する。"""

    def test_a_refused_utterance_is_reported_in_the_actor_result(self) -> None:
        """発話そのものが断られると、行動の結果文に「添えた発言は届かなかった」と出て、ミオには届かない。"""
        with TemporaryDirectory() as tmp:
            wiring = _session(tmp)
            refusing = MagicMock()
            refusing.speak.side_effect = RuntimeError("声が出ない")
            wiring._spot_graph_executor._speech_service = refusing

            result = _try_the_safe_with_a_wrong_code(wiring)

            assert _NOT_DELIVERED in result.message
            assert _heard(wiring, _MIO) == []

    def test_a_delivered_utterance_is_not_reported_as_lost(self) -> None:
        """発言が出せたときは、結果文に「添えた発言は届かなかった」と出ない (正の対照)。"""
        with TemporaryDirectory() as tmp:
            wiring = _session(tmp)

            result = _try_the_safe_with_a_wrong_code(wiring)

            assert _NOT_DELIVERED not in result.message


class TestEveryToolWithWordsDeliversThem:
    """`say_inline` を持つツールは、どれも dispatch の発言の包みを通ることを保証する。"""

    def test_every_tool_offering_say_inline_is_wrapped_to_deliver_the_words(self) -> None:
        """ツール定義に `say_inline` を持つツールは、配線後の handler がすべて発言を出す包みを通る。"""
        with TemporaryDirectory() as tmp:
            wiring = _session(tmp)
            offering = {
                definition.name
                for definition, _ in get_spot_graph_specs()
                if "say_inline" in definition.parameters["properties"]
            }

            unwrapped = {
                name
                for name in offering
                if not getattr(wiring._tool_handlers.get(name), "delivers_say_inline", False)
            }

            assert offering
            assert unwrapped == set()
