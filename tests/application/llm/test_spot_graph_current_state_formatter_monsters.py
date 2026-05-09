"""SpotGraphCurrentStateFormatter のモンスターセクション挙動。

検証対象:
- 生存個体は behavior_label と health_bucket の日本語化を含む
- 死体は専用表記
- monsters_at_spot が空ならセクションごと省略
"""

from __future__ import annotations

import pytest

from ai_rpg_world.application.llm.services.spot_graph_current_state_formatter import (
    SpotGraphCurrentStateFormatter,
)
from ai_rpg_world.application.world.contracts.dtos import PlayerCurrentStateDto
from ai_rpg_world.application.world_graph.spot_graph_current_state_dtos import (
    SpotGraphMonsterEntry,
    SpotGraphPlayerSnapshotDto,
)
from ai_rpg_world.domain.player.enum.player_enum import AttentionLevel


def _make_dto(*monsters: SpotGraphMonsterEntry) -> PlayerCurrentStateDto:
    snap = SpotGraphPlayerSnapshotDto(
        current_spot_id=1,
        current_spot_name="森の入口",
        current_spot_description="",
        travel_status_line=None,
        monsters_at_spot=tuple(monsters),
    )
    return PlayerCurrentStateDto(
        player_id=1,
        player_name="P",
        current_spot_id=1,
        current_spot_name="森の入口",
        current_spot_description="",
        x=None,
        y=None,
        z=None,
        current_player_count=0,
        current_player_ids=set(),
        connected_spot_ids=set(),
        connected_spot_names=set(),
        weather_type="晴れ",
        weather_intensity=0.0,
        current_terrain_type=None,
        visible_objects=[],
        view_distance=0,
        available_moves=None,
        total_available_moves=None,
        attention_level=AttentionLevel.FULL,
        spot_graph_snapshot=snap,
    )


class TestMonsterSection:
    """生存個体・死体・空の各表記。"""

    def test_生存個体は_behavior_と_health_を日本語で含む(self) -> None:
        """落ち着いている・傷を負っている のような日本語が出る。"""
        dto = _make_dto(
            SpotGraphMonsterEntry(
                monster_id=101,
                display_name="灰色のオオカミ",
                behavior_label="落ち着いている",
                health_bucket="wounded",
            )
        )
        text = SpotGraphCurrentStateFormatter().format(dto)

        assert "同じ場所に居るモンスター" in text
        assert "灰色のオオカミ" in text
        assert "落ち着いている" in text
        assert "傷を負っている" in text

    def test_死体は専用表記(self) -> None:
        """is_dead=True の個体は「死骸」表記になる。"""
        dto = _make_dto(
            SpotGraphMonsterEntry(
                monster_id=101,
                display_name="灰色のオオカミ",
                behavior_label="動かない",
                health_bucket="dead",
                is_dead=True,
            )
        )
        text = SpotGraphCurrentStateFormatter().format(dto)

        assert "灰色のオオカミ" in text
        assert "死骸" in text
        # 死体には behavior / health の通常表記は混ぜない（専用文字列のみ）
        assert "傷を負っている" not in text

    def test_モンスター不在ならセクション全体が出ない(self) -> None:
        """monsters_at_spot が空ならヘッダ自体を出さない。"""
        dto = _make_dto()
        text = SpotGraphCurrentStateFormatter().format(dto)

        assert "同じ場所に居るモンスター" not in text

    def test_未知の_health_bucket_はそのまま表示(self) -> None:
        """マップに無い health は raw 文字列が入る（落ちない・潰さない）。"""
        dto = _make_dto(
            SpotGraphMonsterEntry(
                monster_id=101,
                display_name="灰色のオオカミ",
                behavior_label="落ち着いている",
                health_bucket="mystery_state",
            )
        )
        text = SpotGraphCurrentStateFormatter().format(dto)

        assert "mystery_state" in text
