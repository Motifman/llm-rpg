"""SpotGraphUiContextBuilder のモンスターラベル付与挙動。

検証対象:
- M1, M2 とラベルが揮発採番される
- MonsterToolRuntimeTargetDto に monster_id が乗る
- 死体は別表記（死骸）でも同じ M-prefix で targeting 可能
- monsters_at_spot が空なら section 行も target も増えない
"""

from __future__ import annotations

import pytest

from ai_rpg_world.application.llm.contracts.dtos import (
    MonsterToolRuntimeTargetDto,
)
from ai_rpg_world.application.llm.services.spot_graph_ui_context_builder import (
    SpotGraphUiContextBuilder,
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


class TestMonsterLabeling:
    """M1, M2 ラベル + MonsterToolRuntimeTargetDto 登録。"""

    def test_複数個体は_m1_m2_と採番される(self) -> None:
        """先頭から順に M1, M2 を割り当てる（揮発採番）。"""
        dto = _make_dto(
            SpotGraphMonsterEntry(
                monster_id=101,
                display_name="灰色のオオカミ",
                behavior_label="落ち着いている",
                health_bucket="healthy",
            ),
            SpotGraphMonsterEntry(
                monster_id=102,
                display_name="灰色のオオカミ",
                behavior_label="こちらを追っている",
                health_bucket="dying",
            ),
        )
        result = SpotGraphUiContextBuilder().build("base", dto)

        # PR 6 (#404 後続): 同名衝突は ``#N`` で区別。
        # 旧 ``M1: 灰色のオオカミ`` → ``- 灰色のオオカミ #1`` に変更。
        assert "- 灰色のオオカミ #1" in result.current_state_text
        assert "- 灰色のオオカミ #2" in result.current_state_text
        # 旧 M-prefix は prompt 上は出さない
        assert "M1:" not in result.current_state_text
        assert "M2:" not in result.current_state_text
        # ただし内部 collector では label key で保持 (resolver 互換)
        targets = result.tool_runtime_context.targets
        assert "M1" in targets
        assert "M2" in targets
        # display_name は disambiguated 形 (LLM が attack target_label に
        # ``灰色のオオカミ #2`` を渡すと resolver が 2 番目に解決する)
        assert targets["M1"].display_name == "灰色のオオカミ #1"
        assert targets["M2"].display_name == "灰色のオオカミ #2"

    def test_target_に_monster_id_が乗る(self) -> None:
        """ToolRuntimeTargetDto.monster_id にドメイン側 ID が入る。"""
        dto = _make_dto(
            SpotGraphMonsterEntry(
                monster_id=101,
                display_name="灰色のオオカミ",
                behavior_label="落ち着いている",
                health_bucket="healthy",
            )
        )
        result = SpotGraphUiContextBuilder().build("base", dto)
        target = result.tool_runtime_context.targets["M1"]

        assert isinstance(target, MonsterToolRuntimeTargetDto)
        assert target.kind == "spot_graph_monster"
        assert target.monster_id == 101
        assert target.display_name == "灰色のオオカミ"

    def test_死体も同じ_m_prefix_で_target_に登録される(self) -> None:
        """死体も attack 対象にはならないが、M-prefix で内部 target に登録され
        将来 examine 等のツールから参照可能にしておく。

        PR 6 (#404 後続): prompt は ``- 灰色のオオカミ（死骸）`` の名前直書き形式。
        """
        dto = _make_dto(
            SpotGraphMonsterEntry(
                monster_id=101,
                display_name="灰色のオオカミ",
                behavior_label="動かない",
                health_bucket="dead",
                is_dead=True,
            )
        )
        result = SpotGraphUiContextBuilder().build("base", dto)

        assert "- 灰色のオオカミ（死骸）" in result.current_state_text
        assert "M1:" not in result.current_state_text
        target = result.tool_runtime_context.targets["M1"]
        assert isinstance(target, MonsterToolRuntimeTargetDto)
        assert target.monster_id == 101

    def test_モンスター不在のときは_空の事実を明示する(self) -> None:
        """Issue #283 後続の五感対称化: monsters_at_spot が空でも
        「モンスターはいない」事実を明示する。M-prefix の target は当然増えない。
        旧実装は section ごと省略していたため、LLM が「section 無し = いない」を
        暗黙推論する必要があり情報の対称性が崩れていた。"""
        dto = _make_dto()
        result = SpotGraphUiContextBuilder().build("base", dto)

        assert "同じ場所に居るモンスター" in result.current_state_text
        assert "このスポットにモンスターはいない" in result.current_state_text
        # 個体が居ないので M-prefix の target は付かない
        assert all(
            not k.startswith("M") for k in result.tool_runtime_context.targets
        )

    def test_health_と_behavior_がラベル説明に含まれる(self) -> None:
        """説明部分にも behavior と health の日本語が混じる。"""
        dto = _make_dto(
            SpotGraphMonsterEntry(
                monster_id=101,
                display_name="灰色のオオカミ",
                behavior_label="こちらを追っている",
                health_bucket="dying",
            )
        )
        result = SpotGraphUiContextBuilder().build("base", dto)

        assert "こちらを追っている" in result.current_state_text
        assert "瀕死" in result.current_state_text
