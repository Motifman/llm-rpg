"""SpotGraphArgumentResolver の destination/sub_location 引数で
スポット名 (display_name) を直接渡しても解決できることを検証する。

背景:
- 過去 turn の tool_call 履歴に残った `S1` 等のスポット相対ラベルを LLM が
  次 turn でも再利用すると、自スポットが変わると S1 の指す先が反転し
  「閲覧室 ↔ 入口広間」のような bouncing が起きる
- スポット名は不変なので意味が安定し、label leak の影響を受けない
"""

from __future__ import annotations

import pytest

from ai_rpg_world.application.llm.contracts.dtos import (
    DestinationToolRuntimeTargetDto,
    ToolRuntimeContextDto,
    ToolRuntimeTargetDto,
)
from ai_rpg_world.application.llm.services._argument_resolvers.spot_graph_resolver import (
    SpotGraphArgumentResolver,
)
from ai_rpg_world.application.llm.services._resolver_helpers import (
    ToolArgumentResolutionException,
)
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_SPOT_GRAPH_SET_SUB_LOCATION,
    TOOL_NAME_SPOT_GRAPH_TRAVEL_TO,
)


def _make_context() -> ToolRuntimeContextDto:
    return ToolRuntimeContextDto(
        targets={
            "S1": DestinationToolRuntimeTargetDto(
                label="S1",
                kind="spot_graph_destination",
                display_name="入口広間",
                spot_id=10,
                destination_type="spot",
            ),
            "S2": DestinationToolRuntimeTargetDto(
                label="S2",
                kind="spot_graph_destination",
                display_name="閲覧室",
                spot_id=20,
                destination_type="spot",
            ),
            "SL1": ToolRuntimeTargetDto(
                label="SL1",
                kind="spot_graph_sub_location",
                display_name="祭壇前",
                sub_location_id=101,
            ),
            "SL2": ToolRuntimeTargetDto(
                label="SL2",
                kind="spot_graph_sub_location",
                display_name="書架の影",
                sub_location_id=102,
            ),
        },
    )


class TestTravelToByLabel:
    """既存のラベル経由 (S1, S2 等) の解決パスが回帰していないこと。"""

    def test_destination_label_に_S1_を渡すと_spot_id_に解決される(self) -> None:
        """destination_label='S1' で対応する spot_id が返ること（回帰）。"""
        resolver = SpotGraphArgumentResolver()
        result = resolver.resolve_args(
            TOOL_NAME_SPOT_GRAPH_TRAVEL_TO,
            {"destination_label": "S1", "inner_thought": "進む"},
            _make_context(),
        )
        assert result is not None
        assert result["destination_spot_id"] == 10


class TestTravelToByDisplayName:
    """destination_label にスポット名そのものを渡しても解決できること。"""

    def test_destination_label_にスポット名を渡すと_spot_id_に解決される(self) -> None:
        """destination_label='入口広間' でラベル S1 と同じ spot_id が返る。"""
        resolver = SpotGraphArgumentResolver()
        result = resolver.resolve_args(
            TOOL_NAME_SPOT_GRAPH_TRAVEL_TO,
            {"destination_label": "入口広間", "inner_thought": "戻る"},
            _make_context(),
        )
        assert result is not None
        assert result["destination_spot_id"] == 10

    def test_別のスポット名でも対応する_spot_id_に解決される(self) -> None:
        """destination_label='閲覧室' で S2 と同じ spot_id が返る。"""
        resolver = SpotGraphArgumentResolver()
        result = resolver.resolve_args(
            TOOL_NAME_SPOT_GRAPH_TRAVEL_TO,
            {"destination_label": "閲覧室", "inner_thought": "進む"},
            _make_context(),
        )
        assert result is not None
        assert result["destination_spot_id"] == 20

    def test_存在しないスポット名は_INVALID_DESTINATION_LABEL_を投げる(self) -> None:
        """存在しないスポット名は既存と同じ error_code で弾かれる。"""
        resolver = SpotGraphArgumentResolver()
        with pytest.raises(ToolArgumentResolutionException) as exc_info:
            resolver.resolve_args(
                TOOL_NAME_SPOT_GRAPH_TRAVEL_TO,
                {"destination_label": "存在しない部屋", "inner_thought": "?"},
                _make_context(),
            )
        assert exc_info.value.error_code == "INVALID_DESTINATION_LABEL"


class TestTravelToDisplayNameDuplicate:
    """同名スポットが複数ある防御ケース。最初の 1 件を採用する。"""

    def test_同名スポットが複数あっても最初のものが採用される(self) -> None:
        """display_name の重複時は最初にマッチした target の spot_id が返る。"""
        context = ToolRuntimeContextDto(
            targets={
                "S1": DestinationToolRuntimeTargetDto(
                    label="S1",
                    kind="spot_graph_destination",
                    display_name="入口広間",
                    spot_id=10,
                    destination_type="spot",
                ),
                "S2": DestinationToolRuntimeTargetDto(
                    label="S2",
                    kind="spot_graph_destination",
                    display_name="入口広間",
                    spot_id=99,
                    destination_type="spot",
                ),
            },
        )
        resolver = SpotGraphArgumentResolver()
        result = resolver.resolve_args(
            TOOL_NAME_SPOT_GRAPH_TRAVEL_TO,
            {"destination_label": "入口広間", "inner_thought": "進む"},
            context,
        )
        assert result is not None
        # dict 挿入順で最初の S1 の spot_id=10 が採用される
        assert result["destination_spot_id"] == 10


class TestTravelToLenientLabelCandidates:
    """Issue #269 第17回 R2: LLM が prompt 行を貼って destination_label を
    崩すパターンを候補抽出で吸収する。"""

    def test_S2_括弧つきスポット名形式_を解決できる(self) -> None:
        """'S2 (閲覧室)' のような括弧つきラベルでも S2 として解決される。"""
        resolver = SpotGraphArgumentResolver()
        result = resolver.resolve_args(
            TOOL_NAME_SPOT_GRAPH_TRAVEL_TO,
            {"destination_label": "S2 (閲覧室)", "inner_thought": "進む"},
            _make_context(),
        )
        assert result is not None
        assert result["destination_spot_id"] == 20

    def test_S2_コロン区切りで連結されたprompt行を解決できる(self) -> None:
        """'S2: 禁書扉 → 閲覧室' を S2 + 末尾スポット名から解決する。"""
        resolver = SpotGraphArgumentResolver()
        result = resolver.resolve_args(
            TOOL_NAME_SPOT_GRAPH_TRAVEL_TO,
            {"destination_label": "S2: 禁書扉 → 閲覧室", "inner_thought": "進む"},
            _make_context(),
        )
        assert result is not None
        assert result["destination_spot_id"] == 20

    def test_末尾スポット名_と_先頭ラベル_の両方から候補解決できる(self) -> None:
        """'S99 → 入口広間' は S99 (存在せず) を諦め、末尾の '入口広間' で解決する。"""
        resolver = SpotGraphArgumentResolver()
        result = resolver.resolve_args(
            TOOL_NAME_SPOT_GRAPH_TRAVEL_TO,
            {"destination_label": "S99 → 入口広間", "inner_thought": "戻る"},
            _make_context(),
        )
        assert result is not None
        assert result["destination_spot_id"] == 10


class TestNormalizeLabelCandidates:
    """``_normalize_label_candidates`` の抽出パターン。"""

    def test_S2_コロン_矢印_連結文字列の候補(self) -> None:
        from ai_rpg_world.application.llm.services._argument_resolvers.spot_graph_resolver import (
            _normalize_label_candidates,
        )
        c = _normalize_label_candidates("S2: 禁書扉 → 館長書斎")
        assert "S2" in c
        assert "禁書扉" in c
        assert "館長書斎" in c
        # 入力そのものも残る
        assert c[0] == "S2: 禁書扉 → 館長書斎"

    def test_括弧つき注釈はtrailingを剥がして取り出す(self) -> None:
        from ai_rpg_world.application.llm.services._argument_resolvers.spot_graph_resolver import (
            _normalize_label_candidates,
        )
        c = _normalize_label_candidates("S2: 扉 → 館長書斎（通行可）")
        # 末尾の通行可注釈は剥がされた "館長書斎" が候補に出る
        assert "館長書斎" in c

    def test_空文字列は空リスト(self) -> None:
        from ai_rpg_world.application.llm.services._argument_resolvers.spot_graph_resolver import (
            _normalize_label_candidates,
        )
        assert _normalize_label_candidates("") == []
        assert _normalize_label_candidates("   ") == []

    def test_重複候補は除去される(self) -> None:
        from ai_rpg_world.application.llm.services._argument_resolvers.spot_graph_resolver import (
            _normalize_label_candidates,
        )
        c = _normalize_label_candidates("S1")
        assert c == ["S1"]


class TestSetSubLocationByDisplayName:
    """sub_location_label にもサブロケーション名を直接渡せること。"""

    def test_sub_location_label_に_SL1_を渡すと_id_に解決される(self) -> None:
        """既存ラベル経由 (回帰確認): SL1 で対応する sub_location_id が返る。"""
        resolver = SpotGraphArgumentResolver()
        result = resolver.resolve_args(
            TOOL_NAME_SPOT_GRAPH_SET_SUB_LOCATION,
            {"sub_location_label": "SL1", "inner_thought": "移る"},
            _make_context(),
        )
        assert result is not None
        assert result["sub_location_id"] == 101

    def test_sub_location_label_にサブロケーション名を渡すと_id_に解決される(self) -> None:
        """sub_location_label='祭壇前' で SL1 と同じ sub_location_id が返る。"""
        resolver = SpotGraphArgumentResolver()
        result = resolver.resolve_args(
            TOOL_NAME_SPOT_GRAPH_SET_SUB_LOCATION,
            {"sub_location_label": "祭壇前", "inner_thought": "移る"},
            _make_context(),
        )
        assert result is not None
        assert result["sub_location_id"] == 101

    def test_存在しないサブロケーション名は_INVALID_TARGET_LABEL_を投げる(self) -> None:
        """存在しないサブロケーション名は既存と同じ error_code で弾かれる。"""
        resolver = SpotGraphArgumentResolver()
        with pytest.raises(ToolArgumentResolutionException) as exc_info:
            resolver.resolve_args(
                TOOL_NAME_SPOT_GRAPH_SET_SUB_LOCATION,
                {"sub_location_label": "存在しない場所", "inner_thought": "?"},
                _make_context(),
            )
        assert exc_info.value.error_code == "INVALID_TARGET_LABEL"
