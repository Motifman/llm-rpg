"""襲撃の可否と目撃範囲を、部屋の明るさで分ける。

暗がりでしか襲えない従来ルールでは、ランタンを持つ本人が同室を薄暗く
するだけで襲撃を受けなくなっていた。一方、襲撃の観測は明るさに関係なく
``ACTOR_ONLY`` で、同席者にも加害者が見えなかった。

ここでは「明るければ安全」ではなく、「明るければ誰の仕業か分かる」とする。
暗所の匿名性は保ちつつ、明所の襲撃を同席者が目撃できることを公開入口で
固定する。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    InteractionNotAllowedException,
)
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.infrastructure.scenario.scenario_loader import ScenarioLoader

_SCENARIO = (
    Path(__file__).resolve().parents[2] / "data" / "scenarios" / "station_drill.json"
)
_MORI, _SENA, _KUZE, _AOI = (PlayerId(i) for i in range(1, 5))


@pytest.fixture()
def runtime():
    return create_world_runtime(_SCENARIO)


def _move(runtime, player_id: PlayerId, spot: str) -> None:
    """テスト用に player を指定 spot へ直接置き直す。"""
    graph = runtime._spot_graph_repo.find_graph()
    entity_id = EntityId.create(int(player_id))
    graph.unplace_entity(entity_id)
    graph.place_entity(
        entity_id,
        SpotId.create(runtime.id_mapper.get_int("spot", spot)),
    )
    runtime._spot_graph_repo.save(graph)


def _interaction_observations(runtime, player_id: PlayerId):
    """対人 interaction が生んだ観測だけを返す。"""
    return [
        entry.output
        for entry in runtime._obs_buffer.get_observations(player_id)
        if entry.output.structured.get("type") == "player_interacted_with_player"
    ]


class TestAVisibleAttackIsWitnessed:
    """暗がりでない場所の襲撃は、同席者に加害者名つきで届く。"""

    def test_a_bystander_learns_both_names(self, runtime) -> None:
        """明るい集会室の第三者には、加害者と対象の名前が届く。"""
        runtime.do_interact_with_player(_KUZE, _SENA, "strike_down_in_light")

        observations = _interaction_observations(runtime, _MORI)
        assert len(observations) == 1
        assert "クゼ" in observations[0].prose
        assert "セナ" in observations[0].prose

    def test_the_target_message_names_the_attacker(self) -> None:
        """明所襲撃の対象向け文面にも、加害者の名前を差し込める。"""
        scenario = ScenarioLoader().load_from_file(_SCENARIO)
        attack = next(
            interaction
            for interaction in scenario.player_interactions
            if interaction.action_name == "strike_down_in_light"
        )

        assert "{actor}" in (attack.target_observation_message or "")

    def test_a_witness_observation_schedules_the_next_turn(self, runtime) -> None:
        """明所の襲撃を目撃した第三者は、直後に考えて行動できる。"""
        runtime.do_interact_with_player(_KUZE, _SENA, "strike_down_in_light")

        observations = _interaction_observations(runtime, _MORI)
        assert observations[0].schedules_turn is True


class TestAHiddenAttackStaysHidden:
    """暗所襲撃には、従来どおり第三者向けの対人観測を足さない。"""

    def test_a_bystander_gets_no_interaction_observation(self, runtime) -> None:
        """暗い連絡通路の第三者には、襲撃の対人観測が届かない。"""
        for player_id in (_KUZE, _SENA, _MORI):
            _move(runtime, player_id, "corridor")

        runtime.do_interact_with_player(_KUZE, _SENA, "strike_down")

        assert _interaction_observations(runtime, _MORI) == []


class TestAttackVariantsShareOneWait:
    """暗所用と明所用の襲撃を交互に使って待ち時間を迂回できない。"""

    def test_light_then_dark_is_still_waiting(self, runtime) -> None:
        """明所襲撃の直後は、暗所へ移っても暗所襲撃を使えない。"""
        runtime.do_interact_with_player(_KUZE, _SENA, "strike_down_in_light")
        _move(runtime, _KUZE, "corridor")
        _move(runtime, _AOI, "corridor")

        with pytest.raises(InteractionNotAllowedException, match="間を置く"):
            runtime.do_interact_with_player(_KUZE, _AOI, "strike_down")

    def test_dark_then_light_is_still_waiting(self, runtime) -> None:
        """暗所襲撃の直後は、明所へ移っても明所襲撃を使えない。"""
        _move(runtime, _KUZE, "corridor")
        _move(runtime, _SENA, "corridor")
        runtime.do_interact_with_player(_KUZE, _SENA, "strike_down")
        _move(runtime, _KUZE, "hall")

        with pytest.raises(InteractionNotAllowedException, match="間を置く"):
            runtime.do_interact_with_player(_KUZE, _AOI, "strike_down_in_light")


class TestTheWorldExplainsWhatLightChanges:
    """シナリオ本文が、襲撃と灯りの実際の規則に一致する。"""

    def test_public_place_descriptions_do_not_claim_light_prevents_attacks(
        self, runtime
    ) -> None:
        """集会室と連絡通路の描写は、安全や完全な不可視を断定しない。"""
        hall = runtime.build_observation(_KUZE)
        _move(runtime, _KUZE, "corridor")
        corridor = runtime.build_observation(_KUZE)

        assert "誰かに手をかけられる心配はない" not in hall
        assert "居合わせた者には誰の仕業か分かる" in hall
        assert "誰にも見えない" not in corridor
        assert "誰の仕業かまでは分からない" in corridor

    def test_the_impostor_persona_explains_attribution_not_immunity(
        self, runtime
    ) -> None:
        """インポスター本人には、明暗で変わるのは特定可能性だと伝わる。"""
        prompt = runtime.build_system_prompt(_KUZE)

        assert "暗い場所でだけ人を襲える" not in prompt
        assert "暗がりでも灯りのある場所でも人を襲える" in prompt
        assert "誰の仕業か" in prompt

    def test_reading_the_board_delivers_the_shared_light_rule(self, runtime) -> None:
        """当番表を読むと、灯りと通気口の共有規則が経験として届く。"""
        result = runtime.do_interact(_MORI, "duty_board", "read_board")
        message = "\n".join(result.messages)

        assert "灯りのある場所" in message
        assert "誰の仕業か" in message
        assert "暗がりでは分からない" in message
        assert "通気口の格子は、造りを知る者でなければ開かない。" in message
        assert "管理人" not in message
        assert "keeper" not in message

    def test_lantern_authoring_text_matches_the_rule(self) -> None:
        """prompt に未露出の item 説明も、作者向け宣言として実態と一致する。"""
        scenario = ScenarioLoader().load_from_file(_SCENARIO)
        lantern = next(
            item for item in scenario.item_spec_definitions if item.string_id == "lantern"
        )

        assert "持っている人が居る場所は、暗がりではなくなる" not in lantern.description
        assert "誰の仕業か見て取れる" in lantern.description
