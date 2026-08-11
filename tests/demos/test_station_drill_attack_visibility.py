"""襲撃は一つのまま、目撃文だけを部屋の明るさで分ける。

暗がりでしか襲えない従来ルールでは、ランタンを持つ本人が同室を薄暗く
するだけで襲撃を受けなくなっていた。一方、襲撃の観測は明るさに関係なく
``ACTOR_ONLY`` で、同席者にも加害者が見えなかった。

ここでは行為を明暗で二つに割らない。「明るければ誰の仕業か分かる」、
「暗ければ何かが起きたことだけ分かる」を同じ ``strike_down`` の観測文で
表現する。
"""

from __future__ import annotations

import json
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
from tests.demos.station_drill_lighting_helpers import darken_spot

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

    @pytest.mark.parametrize("spot", ["hall", "corridor"])
    def test_the_same_attack_is_available_in_light_and_dark(
        self, runtime, spot: str
    ) -> None:
        """明暗どちらでも入口は ``strike_down`` 一つで、明るさに阻害されない。"""
        if spot == "corridor":
            darken_spot(runtime, spot)
            _move(runtime, _KUZE, spot)
            _move(runtime, _SENA, spot)

        observation = runtime.build_observation(_KUZE)
        row = next(line for line in observation.splitlines() if '"セナ"' in line)

        assert '人を襲う → "strike_down"' in row
        assert "strike_down_in_light" not in observation
        assert "いまは明るい" not in observation
        assert "いまは暗い" not in observation

    def test_a_bystander_learns_both_names(self, runtime) -> None:
        """明るい集会室の第三者には、加害者と対象の名前が届く。"""
        runtime.do_interact_with_player(_KUZE, _SENA, "strike_down")

        observations = _interaction_observations(runtime, _MORI)
        assert len(observations) == 1
        assert "クゼ" in observations[0].prose
        assert "セナ" in observations[0].prose

    def test_the_target_message_remains_anonymous(self) -> None:
        """目撃文の選択を足しても、被害者本人向けの匿名文は変えない。"""
        scenario = ScenarioLoader().load_from_file(_SCENARIO)
        attack = next(
            interaction
            for interaction in scenario.player_interactions
            if interaction.action_name == "strike_down"
        )

        assert attack.target_observation_message == (
            "闇の中で強い衝撃を受けた。誰にやられたのか分からない。"
        )

    def test_a_witness_observation_schedules_the_next_turn(self, runtime) -> None:
        """明所の襲撃を目撃した第三者は、直後に考えて行動できる。"""
        runtime.do_interact_with_player(_KUZE, _SENA, "strike_down")

        observations = _interaction_observations(runtime, _MORI)
        assert observations[0].schedules_turn is True


class TestAHiddenAttackStaysHidden:
    """暗所襲撃は、身元を伏せた証拠だけを同席者へ残す。"""

    def test_a_bystander_gets_an_anonymous_observation(self, runtime) -> None:
        """暗い連絡通路の第三者には匿名文が届き、構造化情報にも行為者が無い。"""
        darken_spot(runtime, "corridor")
        for player_id in (_KUZE, _SENA, _MORI):
            _move(runtime, player_id, "corridor")

        runtime.do_interact_with_player(_KUZE, _SENA, "strike_down")

        observations = _interaction_observations(runtime, _MORI)
        assert len(observations) == 1
        assert observations[0].prose == "暗がりで、何かがぶつかる鈍い音がした。"
        assert "クゼ" not in observations[0].prose
        assert "actor" not in observations[0].structured

    def test_unknown_lighting_uses_the_anonymous_message(self, runtime) -> None:
        """照明を解決できないとき、明所文で身元を漏らさず暗所文へ倒す。"""
        runtime._player_interaction_service._effective_lighting_resolver = None

        runtime.do_interact_with_player(_KUZE, _SENA, "strike_down")

        observations = _interaction_observations(runtime, _MORI)
        assert observations[0].prose == "暗がりで、何かがぶつかる鈍い音がした。"
        assert "actor" not in observations[0].structured

    def test_undeclared_dark_message_keeps_the_bright_message(
        self, tmp_path: Path
    ) -> None:
        """暗所文を宣言しない既存 interaction は、暗さによらず従来文を使う。"""
        raw = json.loads(_SCENARIO.read_text(encoding="utf-8"))
        attack = next(
            item
            for item in raw["player_interactions"]
            if item["action_name"] == "strike_down"
        )
        attack.pop("witness_observation_message_in_dark", None)
        path = tmp_path / "strike_without_dark_message.json"
        path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
        runtime = create_world_runtime(path)
        darken_spot(runtime, "corridor")
        for player_id in (_KUZE, _SENA, _MORI):
            _move(runtime, player_id, "corridor")

        runtime.do_interact_with_player(_KUZE, _SENA, "strike_down")

        observation = _interaction_observations(runtime, _MORI)[0]
        assert "クゼ" in observation.prose
        assert observation.structured["actor"] == "クゼ"


class TestOneAttackKeepsOneWait:
    """一つの襲撃は、明暗を移っても同じ待ち時間を使う。"""

    def test_light_then_dark_is_still_waiting(self, runtime) -> None:
        """明所で襲った直後は、暗所へ移っても同じ襲撃を使えない。"""
        scenario = ScenarioLoader().load_from_file(_SCENARIO)
        attack = next(
            item for item in scenario.player_interactions
            if item.action_name == "strike_down"
        )
        assert attack.cooldown_group is None

        runtime.do_interact_with_player(_KUZE, _SENA, "strike_down")
        darken_spot(runtime, "corridor")
        _move(runtime, _KUZE, "corridor")
        _move(runtime, _AOI, "corridor")

        with pytest.raises(InteractionNotAllowedException, match="間を置く"):
            runtime.do_interact_with_player(_KUZE, _AOI, "strike_down")

    def test_dark_then_light_is_still_waiting(self, runtime) -> None:
        """暗所で襲った直後は、明所へ移っても同じ襲撃を使えない。"""
        darken_spot(runtime, "corridor")
        _move(runtime, _KUZE, "corridor")
        _move(runtime, _SENA, "corridor")
        runtime.do_interact_with_player(_KUZE, _SENA, "strike_down")
        _move(runtime, _KUZE, "hall")

        with pytest.raises(InteractionNotAllowedException, match="間を置く"):
            runtime.do_interact_with_player(_KUZE, _AOI, "strike_down")


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
