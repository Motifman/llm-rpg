"""幽霊の出る世界で、say と囁きが届く相手の組み合わせを設計表どおりに保証する。

実 run で、死者の say は同じ場所の死者に届くのに、死者同士の囁きだけが
「死亡しており届きません」で拒否された。say が届いたことから「死者同士は
聞こえる」と学んだエージェントが囁きを繰り返し失敗し続けた。

生者から死者への囁きは拒否のまま残す。遺体から離れた幽霊について「同じ
スポットにいません」と返すと目の前に遺体がある生者の視点と食い違い、
届いたかどうかの出し分けで特定の人の幽霊がその場にいるかが分かってしまう。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.player.enum.player_outcome_enum import PlayerOutcomeEnum
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.presentation.spot_graph_game.runtime_manager import _WorldLlmWiring

_SCENARIO = Path(__file__).resolve().parents[2] / "data" / "scenarios" / "station_drill.json"
_SENA = PlayerId(2)
_KUZE = PlayerId(3)
_SPOT = "corridor"


class _StubClient:
    """LLM は呼ばず、実際のツール境界だけを通す。"""


def _spot(runtime, name: str) -> SpotId:
    return SpotId.create(runtime.id_mapper.get_int("spot", name))


def _place_living(runtime, player_id: PlayerId, spot_name: str) -> None:
    graph = runtime._spot_graph_repo.find_graph()
    entity_id = EntityId.create(int(player_id))
    graph.unplace_entity(entity_id)
    graph.place_entity(entity_id, _spot(runtime, spot_name))
    runtime._spot_graph_repo.save(graph)


def _make_dead(runtime, player_id: PlayerId, spot_name: str) -> None:
    _place_living(runtime, player_id, spot_name)
    runtime._fallen_body_registry.record(player_id, _spot(runtime, spot_name), WorldTick(runtime.current_tick()))
    status = runtime._player_status_repo.find_by_id(player_id)
    status.apply_damage(status.hp.value)
    runtime._player_status_repo.save(status)
    runtime._player_outcome_registry.set_outcome(player_id, PlayerOutcomeEnum.DEAD)
    runtime._departed_position_store.place(player_id, _spot(runtime, spot_name))


def _speak(runtime, speaker: PlayerId, arguments: dict):
    """話し手の手番文脈を組み立て、speak ツールを実ツール境界で実行する。"""
    context = runtime.build_llm_context(speaker).tool_runtime_context
    wiring = _WorldLlmWiring(
        runtime=runtime,
        observation_buffer=runtime._obs_buffer,
        short_term_memory=runtime._short_term_memory,
        llm_client=_StubClient(),
    )
    return wiring._execute_tool(
        speaker,
        "speak",
        arguments,
        context,
        offered_tools_at_prompt={"speak": None},
    )


def _label_of(runtime, speaker: PlayerId, listener: PlayerId) -> str:
    targets = runtime.build_llm_context(speaker).tool_runtime_context.targets
    return next(label for label, target in targets.items() if getattr(target, "player_id", None) == int(listener))


def _heard(runtime, listener: PlayerId, content: str) -> bool:
    return any(
        content in str(entry.output.structured.get("content", ""))
        for entry in runtime._obs_buffer.get_observations(listener)
    )


def _setup(speaker_dead: bool, listener_dead: bool):
    runtime = create_world_runtime(_SCENARIO)
    speaker, listener = _SENA, _KUZE
    for player_id, dead in ((speaker, speaker_dead), (listener, listener_dead)):
        if dead:
            _make_dead(runtime, player_id, _SPOT)
        else:
            _place_living(runtime, player_id, _SPOT)
    return runtime, speaker, listener


_SAY_TABLE = [
    pytest.param(False, False, True, id="living_to_living"),
    pytest.param(False, True, True, id="living_to_departed"),
    pytest.param(True, False, False, id="departed_to_living"),
    pytest.param(True, True, True, id="departed_to_departed"),
]

_WHISPER_TABLE = [
    pytest.param(False, False, True, None, id="living_to_living"),
    pytest.param(False, True, False, "INVALID_WHISPER", id="living_to_departed"),
    pytest.param(True, False, False, None, id="departed_to_living"),
    pytest.param(True, True, True, None, id="departed_to_departed"),
]


class TestDepartedWhisperMatchesSay:
    """station_drill で、生者と死者の四つの組み合わせについて say と囁きの到達を設計表どおりに保証する。"""

    @pytest.mark.parametrize("speaker_dead,listener_dead,expected", _SAY_TABLE)
    def test_say_reaches_listener_as_in_the_design_table(
        self, speaker_dead: bool, listener_dead: bool, expected: bool
    ) -> None:
        """同じ場所の相手に say すると、生者が死者の声を聞く組み合わせだけ届かず、それ以外は相手の観測に入る。"""
        runtime, speaker, listener = _setup(speaker_dead, listener_dead)

        _speak(runtime, speaker, {"channel": "say", "content": "聞こえるか"})

        assert _heard(runtime, listener, "聞こえるか") is expected

    @pytest.mark.parametrize("speaker_dead,listener_dead,expected,error_code", _WHISPER_TABLE)
    def test_whisper_reaches_listener_as_in_the_design_table(
        self,
        speaker_dead: bool,
        listener_dead: bool,
        expected: bool,
        error_code: str | None,
    ) -> None:
        """同じ場所の相手に囁くと、生→生と死→死は相手の観測に入り、死→生は届かず、生→死は INVALID_WHISPER で拒否される。"""
        runtime, speaker, listener = _setup(speaker_dead, listener_dead)
        label = _label_of(runtime, speaker, listener)

        result = _speak(
            runtime,
            speaker,
            {"channel": "whisper", "content": "内緒の話", "target_label": label},
        )

        assert _heard(runtime, listener, "内緒の話") is expected
        assert result.error_code == error_code

    def test_departed_whisper_to_departed_succeeds_and_reports_delivery(self) -> None:
        """死者が同じ場所の死者に囁くと INVALID_WHISPER にならず、結果に「囁きが届いた」と返る。"""
        runtime, speaker, listener = _setup(speaker_dead=True, listener_dead=True)
        label = _label_of(runtime, speaker, listener)

        result = _speak(
            runtime,
            speaker,
            {"channel": "whisper", "content": "内緒の話", "target_label": label},
        )

        assert result.success is True
        assert "囁きが届いた" in result.message

    def test_departed_whisper_to_living_reports_no_delivery(self) -> None:
        """死者が同じ場所の生者に囁くと、say と同じく誰にも届かなかったと返り、届いたとは言わない。"""
        runtime, speaker, listener = _setup(speaker_dead=True, listener_dead=False)
        label = _label_of(runtime, speaker, listener)

        result = _speak(
            runtime,
            speaker,
            {"channel": "whisper", "content": "内緒の話", "target_label": label},
        )

        assert "囁きが届いた" not in result.message
        assert "誰にも届きませんでした" in result.message

    @pytest.mark.parametrize("ghost_spot", [_SPOT, "storage"], ids=["ghost_at_body", "ghost_moved_away"])
    def test_living_whisper_to_body_is_rejected_without_revealing_ghost_position(self, ghost_spot: str) -> None:
        """生者が同じ場所の遺体に囁くと、幽霊がその場にいても移動済みでも同じ「死亡しており、囁きは届きません」で拒否され、結果文から幽霊の位置が分からない。"""
        runtime, speaker, listener = _setup(speaker_dead=False, listener_dead=True)
        runtime._departed_position_store.move(listener, _spot(runtime, ghost_spot))
        label = _label_of(runtime, speaker, listener)

        result = _speak(
            runtime,
            speaker,
            {"channel": "whisper", "content": "内緒の話", "target_label": label},
        )

        assert result.success is False
        assert result.error_code == "INVALID_WHISPER"
        assert result.message == ("囁きを送れませんでした: クゼは死亡しており、囁きは届きません。")
        assert not _heard(runtime, listener, "内緒の話")
