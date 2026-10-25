"""players[].appearance のパースと、名前を知らない相手を見た目で出すための読み込み時の検証 (#1581)。"""

from __future__ import annotations

import copy
from typing import Any

import pytest
from tests.infrastructure.scenario.test_scenario_loader import _minimal_scenario

from ai_rpg_world.infrastructure.scenario.scenario_loader import (
    ScenarioLoader,
    ScenarioLoadError,
)


def _two_strangers(**overrides: Any) -> dict[str, Any]:
    """互いを紹介しない 2 人のシナリオ。overrides は player id ごとに項目を上書きする。"""
    scenario = copy.deepcopy(_minimal_scenario())
    scenario["players"] = [
        {
            "id": "p1",
            "name": "エイダ",
            "spawn_spot": "room_a",
            "initial_items": [],
            "knows_at_start": [],
            "appearance": "外套の女",
        },
        {
            "id": "p2",
            "name": "ノア",
            "spawn_spot": "room_a",
            "initial_items": [],
            "knows_at_start": [],
            "appearance": "背の高い男",
        },
    ]
    for player in scenario["players"]:
        player.update(overrides.get(player["id"], {}))
    return scenario


class TestAppearanceDeclaration:
    """appearance の宣言あり・なしで PlayerSpawnConfig が保持する値を保証する。"""

    def test_declared_appearance_is_kept_stripped(self) -> None:
        """appearance に書いた句は、前後の空白を落として保持される。"""
        result = ScenarioLoader().load_from_dict(_two_strangers(p1={"appearance": "  外套の女 "}))

        assert result.player_spawns[0].appearance == "外套の女"

    def test_unspecified_appearance_is_none_when_everyone_is_introduced(self) -> None:
        """全員を紹介するシナリオでは、appearance を書かなくてよく None になる。"""
        scenario = _two_strangers()
        for player in scenario["players"]:
            del player["knows_at_start"]
            del player["appearance"]

        result = ScenarioLoader().load_from_dict(scenario)

        assert [s.appearance for s in result.player_spawns] == [None, None]


class TestAppearanceValidation:
    """名前を知らない相手を出す手段が無いシナリオと、見た目から名前が分かるシナリオを読み込み時に止めることを保証する。"""

    def test_stranger_without_appearance_is_rejected(self) -> None:
        """誰かが最初から知らない人に appearance が無いと、その人を示して ScenarioLoadError を投げる。"""
        scenario = _two_strangers()
        del scenario["players"][1]["appearance"]

        with pytest.raises(ScenarioLoadError, match=r"players\[p2\]\.appearance"):
            ScenarioLoader().load_from_dict(scenario)

    def test_player_known_to_everyone_needs_no_appearance(self) -> None:
        """全員が最初から知っている人は、appearance が無くても読み込める。"""
        scenario = _two_strangers(p1={"knows_at_start": ["p2"]})
        del scenario["players"][1]["appearance"]

        result = ScenarioLoader().load_from_dict(scenario)

        assert result.player_spawns[1].appearance is None

    @pytest.mark.parametrize("value", ["", "   ", 3, None], ids=["empty", "blank", "int", "null"])
    def test_blank_or_non_string_appearance_is_rejected(self, value: Any) -> None:
        """appearance が空・空白だけ・文字列でない・null なら ScenarioLoadError を投げる。"""
        with pytest.raises(ScenarioLoadError, match="appearance"):
            ScenarioLoader().load_from_dict(_two_strangers(p2={"appearance": value}))

    def test_shared_appearance_is_rejected(self) -> None:
        """2 人が同じ appearance だと、どちらを指すか決まらないので ScenarioLoadError を投げる。"""
        with pytest.raises(ScenarioLoadError, match="appearance"):
            ScenarioLoader().load_from_dict(_two_strangers(p2={"appearance": "外套の女"}))

    def test_appearance_containing_a_name_is_rejected(self) -> None:
        """appearance に参加者の名前が入っていると、見た目から名前が漏れるので ScenarioLoadError を投げる。"""
        with pytest.raises(ScenarioLoadError, match="appearance"):
            ScenarioLoader().load_from_dict(_two_strangers(p2={"appearance": "エイダの連れ"}))

    def test_name_inside_another_name_is_rejected(self) -> None:
        """ある人の名前が別の人の名前の一部だと、名前を置き換えるときに別の人まで巻き込むので ScenarioLoadError を投げる。"""
        with pytest.raises(ScenarioLoadError, match="name"):
            ScenarioLoader().load_from_dict(_two_strangers(p2={"name": "エイダン"}))

    @pytest.mark.parametrize("field", ["persona_prompt", "objective"])
    def test_text_naming_an_unknown_player_is_rejected(self, field: str) -> None:
        """persona や目的に、その人が最初から知らない相手の名前を書くと ScenarioLoadError を投げる。"""
        scenario = _two_strangers(p1={field: "ノアを探す。"})

        with pytest.raises(ScenarioLoadError, match=rf"players\[p1\]\.{field}"):
            ScenarioLoader().load_from_dict(scenario)

    @pytest.mark.parametrize("field", ["persona_prompt", "objective"])
    def test_text_naming_self_or_known_player_is_accepted(self, field: str) -> None:
        """persona や目的に、自分の名前と最初から知っている相手の名前は書ける。"""
        scenario = _two_strangers(p1={field: "エイダはノアを探す。", "knows_at_start": ["p2"]})

        result = ScenarioLoader().load_from_dict(scenario)

        assert result.player_spawns[0].knows_at_start == ("p2",)
