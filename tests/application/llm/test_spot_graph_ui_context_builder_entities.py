"""SpotGraphUiContextBuilder の同 spot プレイヤー (entity) 表示挙動。

Issue #283 後続の五感対称化:
- 旧実装は nearby_entities が空のとき section ごと省略していたため、
  LLM は「section 無し = 誰もいない」を暗黙推論する必要があった。R1 の
  speech 誤用 (相手が居るか分からないまま SHOUT) はこの曖昧さが温床。
- 新実装は「居ても居なくても section を出す」(対称な情報提示)。
"""

from __future__ import annotations

from ai_rpg_world.application.llm.contracts.dtos import PlayerToolRuntimeTargetDto
from ai_rpg_world.application.llm.services.spot_graph_ui_context_builder import (
    SpotGraphUiContextBuilder,
)
from ai_rpg_world.application.world.contracts.dtos import PlayerCurrentStateDto
from ai_rpg_world.application.world_graph.spot_graph_current_state_dtos import (
    SpotGraphNearbyEntityEntry,
    SpotGraphPlayerSnapshotDto,
)
from ai_rpg_world.domain.player.enum.player_enum import AttentionLevel


def _make_dto(*entities: SpotGraphNearbyEntityEntry) -> PlayerCurrentStateDto:
    snap = SpotGraphPlayerSnapshotDto(
        current_spot_id=1,
        current_spot_name="広間",
        current_spot_description="",
        travel_status_line=None,
        nearby_entities=tuple(entities),
    )
    return PlayerCurrentStateDto(
        player_id=1,
        player_name="P",
        current_spot_id=1,
        current_spot_name="広間",
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


class TestNearbyEntityLabeling:
    """PR 6 後 (#404 後続): 名前直書き + PlayerToolRuntimeTargetDto 登録。"""

    def test_居れば_名前で_行が出る(self) -> None:
        """PR 6: 旧 ``P1: リン`` → ``- リン`` に簡略化 (ラベル prefix を捨てる)。"""
        dto = _make_dto(
            SpotGraphNearbyEntityEntry(entity_id=2, display_name="リン"),
            SpotGraphNearbyEntityEntry(entity_id=3, display_name="カイト"),
        )
        result = SpotGraphUiContextBuilder().build("base", dto)
        assert "同じ場所にいるプレイヤー:" in result.current_state_text
        assert '- "リン"' in result.current_state_text
        assert '- "カイト"' in result.current_state_text
        # 旧ラベル prefix は出さない
        assert "P1:" not in result.current_state_text
        assert "P2:" not in result.current_state_text
        # target には内部 label で登録される (resolver の互換のため)
        targets = result.tool_runtime_context.targets
        assert isinstance(targets["P1"], PlayerToolRuntimeTargetDto)
        assert targets["P1"].player_id == 2
        assert targets["P2"].player_id == 3

    def test_display_name_が空でも_fallback_ラベルになる(self) -> None:
        dto = _make_dto(
            SpotGraphNearbyEntityEntry(entity_id=2, display_name=""),
        )
        result = SpotGraphUiContextBuilder().build("base", dto)
        # PR 6: ``- プレイヤー(2)`` 形式
        assert '- "プレイヤー(2)"' in result.current_state_text
        assert "P1:" not in result.current_state_text


class TestNearbyEntityEmptySymmetric:
    """Issue #283: 不在のときも明示する (対称化)。"""

    def test_他プレイヤー不在のときは_いない事実を明示する(self) -> None:
        """旧実装は section 自体を省略していたが、LLM が「いない」を確信
        できないと speech の誤用 (相手が同 spot に居る前提で SAY) が起きる。
        いない事実を明示する。"""
        dto = _make_dto()
        result = SpotGraphUiContextBuilder().build("base", dto)
        assert "同じ場所にいるプレイヤー" in result.current_state_text
        assert "他のプレイヤーはこのスポットにいない" in result.current_state_text

    def test_不在のときは_P_prefix_target_は登録されない(self) -> None:
        """文面に '同じ場所にいるプレイヤー: (...)' は出すが、P-prefix の
        target dict は当然空。speech_speak の target_label として P1 等を
        提示しないことで「いない相手に whisper する」誤用を阻止。"""
        dto = _make_dto()
        result = SpotGraphUiContextBuilder().build("base", dto)
        targets = result.tool_runtime_context.targets
        assert all(not k.startswith("P") for k in targets)
