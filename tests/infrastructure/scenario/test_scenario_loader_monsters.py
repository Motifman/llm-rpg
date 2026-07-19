"""ScenarioLoader の monsters ブロックパース検証 (Phase B-2a)。

JSON → ScenarioMonsterTemplate (MonsterTemplate) と ScenarioMonsterPlacement
への変換、および境界エラーを確認する。
"""

from __future__ import annotations

import pytest

from ai_rpg_world.infrastructure.scenario.scenario_id_mapper import ScenarioIdMapper
from ai_rpg_world.infrastructure.scenario.scenario_loader import (
    ScenarioLoadError,
    ScenarioLoader,
    ScenarioMonsterPlacement,
    ScenarioMonsterTemplate,
)
from ai_rpg_world.domain.monster.enum.monster_enum import MonsterFactionEnum
from ai_rpg_world.domain.player.enum.player_enum import Race


def _minimal_template(template_id: str = "wild_dog") -> dict:
    return {
        "id": template_id,
        "name": "野犬",
        "description": "島を彷徨う飢えた野犬。",
        "race": "WOLF",
        "faction": "ENEMY",
        "base_stats": {
            "max_hp": 30, "max_mp": 0, "attack": 8, "defense": 4,
            "speed": 6, "critical_rate": 0.05, "evasion_rate": 0.1,
        },
        "reward": {"exp": 10, "gold": 0},
        "respawn": {"interval_ticks": 50, "auto": True},
        "vision_range": 4,
        "flee_threshold": 0.2,
    }


def _minimal_placement(template_id: str = "wild_dog", spot: str = "deep_forest") -> dict:
    return {"template": template_id, "spot": spot, "coordinate": {"x": 0, "y": 0}}


class TestParseMonsterTemplates:
    """templates 配下の JSON を MonsterTemplate に変換する経路。"""

    def test_min_template_monster_template(self) -> None:
        """name / race / faction / base_stats / reward / respawn が反映される。"""
        loader = ScenarioLoader()
        mapper = ScenarioIdMapper()
        templates, _ = loader._parse_monsters_block(
            {"templates": [_minimal_template()]}, mapper,
        )
        assert len(templates) == 1
        st = templates[0]
        assert isinstance(st, ScenarioMonsterTemplate)
        assert st.string_id == "wild_dog"
        assert st.template.name == "野犬"
        assert st.template.race == Race.WOLF
        assert st.template.faction == MonsterFactionEnum.ENEMY
        assert st.template.base_stats.max_hp == 30
        assert st.template.base_stats.attack == 8
        assert st.template.reward_info.exp == 10
        assert st.template.respawn_info.respawn_interval_ticks == 50
        # id_mapper にも登録される
        assert mapper.contains("monster_template", "wild_dog")

    def test_id_empty_scenario_load_error(self) -> None:
        """template.id 必須 (作家ミス防止)。"""
        loader = ScenarioLoader()
        with pytest.raises(ScenarioLoadError):
            loader._parse_monsters_block(
                {"templates": [{**_minimal_template(), "id": ""}]},
                ScenarioIdMapper(),
            )

    def test_race_invalid_scenario_load_error(self) -> None:
        """Race enum に無い名前は boundary で弾く。"""
        loader = ScenarioLoader()
        with pytest.raises(ScenarioLoadError):
            loader._parse_monsters_block(
                {"templates": [{**_minimal_template(), "race": "NOT_A_RACE"}]},
                ScenarioIdMapper(),
            )

    def test_faction_invalid_scenario_load_error(self) -> None:
        """faction が不正だと ScenarioLoadError。"""
        loader = ScenarioLoader()
        with pytest.raises(ScenarioLoadError):
            loader._parse_monsters_block(
                {"templates": [{**_minimal_template(), "faction": "UNKNOWN"}]},
                ScenarioIdMapper(),
            )

    def test_base_stats_dict_scenario_load_error(self) -> None:
        """base stats が dict でないと ScenarioLoadError。"""
        loader = ScenarioLoader()
        with pytest.raises(ScenarioLoadError):
            loader._parse_monsters_block(
                {"templates": [{**_minimal_template(), "base_stats": "x"}]},
                ScenarioIdMapper(),
            )


class TestParseMonsterPlacements:
    """initial_placements を ScenarioMonsterPlacement に変換する経路。"""

    def test_min_placement(self) -> None:
        """最小限の placement が変換される。"""
        loader = ScenarioLoader()
        _, placements = loader._parse_monsters_block(
            {
                "templates": [_minimal_template()],
                "initial_placements": [_minimal_placement()],
            },
            ScenarioIdMapper(),
        )
        assert len(placements) == 1
        p = placements[0]
        assert isinstance(p, ScenarioMonsterPlacement)
        assert p.template_string_id == "wild_dog"
        assert p.spot_string_id == "deep_forest"
        assert p.coordinate_x == 0

    def test_coordinate_xyz_zero(self) -> None:
        """coordinate を渡さなくても (0,0,0) で構築できる。"""
        loader = ScenarioLoader()
        _, placements = loader._parse_monsters_block(
            {
                "templates": [_minimal_template()],
                "initial_placements": [{"template": "wild_dog", "spot": "deep_forest"}],
            },
            ScenarioIdMapper(),
        )
        assert placements[0].coordinate_x == 0
        assert placements[0].coordinate_y == 0
        assert placements[0].coordinate_z == 0

    def test_template_empty_string_scenario_load_error(self) -> None:
        """template が空文字なら ScenarioLoadError。"""
        loader = ScenarioLoader()
        with pytest.raises(ScenarioLoadError):
            loader._parse_monsters_block(
                {
                    "initial_placements": [{"template": "", "spot": "deep_forest"}],
                },
                ScenarioIdMapper(),
            )

    def test_spot_empty_string_scenario_load_error(self) -> None:
        """spot が空文字なら ScenarioLoadError。"""
        loader = ScenarioLoader()
        with pytest.raises(ScenarioLoadError):
            loader._parse_monsters_block(
                {
                    "initial_placements": [{"template": "wild_dog", "spot": ""}],
                },
                ScenarioIdMapper(),
            )


class TestParseMonstersBlockOptional:
    """monsters セクション自体が無いシナリオは empty を返す。"""

    def test_none_empty_tuple(self) -> None:
        """None なら 空タプル。"""
        loader = ScenarioLoader()
        t, p = loader._parse_monsters_block(None, ScenarioIdMapper())
        assert t == ()
        assert p == ()

    def test_empty_dict_empty_tuple(self) -> None:
        """空辞書なら 空タプル。"""
        loader = ScenarioLoader()
        t, p = loader._parse_monsters_block({}, ScenarioIdMapper())
        assert t == ()
        assert p == ()
