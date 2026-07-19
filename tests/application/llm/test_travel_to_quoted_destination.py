"""travel_to の destination_label 解決を edge/spot 名衝突に耐えるよう強化したか
を検証する (Y_after_pr_all_200tick 後続)。

Y_after_pr_all_200tick で observe された問題:
- ``spot_graph_travel_to`` の失敗 14 件はすべて ``INVALID_DESTINATION_LABEL``
- inner_thought では LLM は行き先の spot 名を正しく把握している (例:
  「拠点方面へ向かう」「森の広場で待っている」)
- しかし渡している値は edge 名 (= ``connection_name``) で、prompt の
  ``- 浜辺の砂道 → 拠点（通行可）`` の左側を選んでいる
- 致命的なのは「森への入口 → 森の入口」のように edge 名と spot 名が
  "の/への" 1 文字違いのケース。LLM は判断できない

prompt の表記 (= 動的セクション側) と tool description (= 静的セクション側)
の両方を直し、加えて resolver にも shadow entry / quote strip の安全網を
入れる。

### 変更点

1. **prompt 表記**: ``- 浜辺の砂道 → "拠点"（通行可）`` のように右側
   (= 渡すべき spot 名) を ``""`` で囲む。LLM は「``""`` 内が tool に
   渡す値」という汎用規約で読める
2. **tool description**: destination_label の description で
   「``""`` で囲まれた spot 名をそのまま渡す」と明示
3. **resolver の quote strip**: LLM が ``'"拠点"'`` のように quote ごと
   渡しても resolve できる
4. **shadow entry**: 接続先 1 件につき edge 名でも引ける shadow target を
   登録する。これにより LLM が誤って edge 名を渡しても resolver が
   destination spot に飛ばす (silent rescue)。``list_destination_labels``
   からは ``__edge_`` prefix で除外
"""

from __future__ import annotations

import pytest

from ai_rpg_world.application.llm.contracts.dtos import (
    DestinationToolRuntimeTargetDto,
    ToolRuntimeContextDto,
)
from ai_rpg_world.application.llm.services._argument_resolvers.spot_graph_resolver import (
    resolve_destination_target,
    _normalize_label_candidates,
)
from ai_rpg_world.application.llm.services._resolver_helpers import (
    ToolArgumentResolutionException,
)
from ai_rpg_world.application.llm.services.failure_helpers import (
    list_destination_labels,
)
from ai_rpg_world.application.llm.services.spot_graph_ui_context_builder import (
    SpotGraphUiContextBuilder,
)
from ai_rpg_world.application.llm.services.tool_catalog.spot_graph import (
    TRAVEL_TO_DEFINITION,
)
from ai_rpg_world.application.world.contracts.dtos import PlayerCurrentStateDto
from ai_rpg_world.application.world_graph.spot_graph_current_state_dtos import (
    SpotGraphConnectionEntry,
    SpotGraphPlayerSnapshotDto,
)
from ai_rpg_world.domain.player.enum.player_enum import AttentionLevel


def _make_dto(snap: SpotGraphPlayerSnapshotDto) -> PlayerCurrentStateDto:
    return PlayerCurrentStateDto(
        player_id=1,
        player_name="P",
        current_spot_id=snap.current_spot_id,
        current_spot_name=snap.current_spot_name,
        current_spot_description=snap.current_spot_description,
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


def _snap_two_edges() -> SpotGraphPlayerSnapshotDto:
    """edge 名と spot 名が紛らわしいケース (実 trace で観測された "森への入口/森の入口" を模す)。"""
    return SpotGraphPlayerSnapshotDto(
        current_spot_id=1,
        current_spot_name="浜辺",
        current_spot_description="砂浜",
        travel_status_line=None,
        connections=(
            SpotGraphConnectionEntry(
                destination_spot_id=2,
                connection_name="浜辺の砂道",
                destination_spot_name="拠点",
                is_passable=True,
            ),
            SpotGraphConnectionEntry(
                destination_spot_id=3,
                connection_name="森への入口",
                destination_spot_name="森の入口",
                is_passable=True,
            ),
        ),
    )


class TestPromptQuotesDestinationSpotName:
    """prompt 上で「渡すべき値」(spot 名) が ``""`` で囲まれる。"""

    def test_prompt_quotes_destination_spot_name(self) -> None:
        """LLM が arrow の右側 (= spot 名) を「渡すべき値」と読み取れるよう、
        spot 名のみ ``""`` で囲む。edge 名は囲まない (= 視覚的に区別)。"""
        result = SpotGraphUiContextBuilder().build(
            "現在地: 浜辺", _make_dto(_snap_two_edges())
        )
        text = result.current_state_text
        assert '"拠点"' in text, "spot 名 (右側) が \"\" で囲まれていない"
        assert '"森の入口"' in text, "2 件目の spot 名も \"\" で囲まれること"

    def test_prompt_edge(self) -> None:
        """edge 名 (左側) は囲まない。``""`` の有無で「渡すべき値」を区別する。"""
        result = SpotGraphUiContextBuilder().build(
            "現在地: 浜辺", _make_dto(_snap_two_edges())
        )
        text = result.current_state_text
        # 行レベルで確認: edge 名行は "浜辺の砂道 → ..." の形式で、edge 名自体が
        # quote されていないこと
        assert '"浜辺の砂道"' not in text, "edge 名は \"\" で囲まないこと"
        assert '"森への入口"' not in text, "edge 名は \"\" で囲まないこと"


class TestTravelToDescriptionExplainsQuoteConvention:
    """tool description が ``""`` 規約を伝える。"""

    def test_destination_label_description_included(self) -> None:
        """『現在の状況の "..." で囲まれた spot 名をそのまま渡す』のような
        記述で、prompt 表記と引数の対応を明示する。"""
        desc = TRAVEL_TO_DEFINITION.parameters["properties"]["destination_label"][
            "description"
        ]
        # ``""`` が prompt 上の規約として登場することを明示
        assert "\"" in desc, "description に quote の例示がない"
        # 説明文脈: 「囲まれた」「クオート」「\"\"」のいずれかを含む
        assert (
            "囲ま" in desc or "クオート" in desc or "ダブルクォート" in desc
        ), "「\"\" で囲まれた値を渡す」規約が説明されていない"

    def test_destination_label_description_string(self) -> None:
        """description は static (prefix cache 安全)。"""
        desc = TRAVEL_TO_DEFINITION.parameters["properties"]["destination_label"][
            "description"
        ]
        assert isinstance(desc, str)
        assert "{" not in desc, "placeholder の疑い"


class TestNormalizeLabelCandidatesStripsQuotes:
    """LLM が ``""`` ごと渡してきた場合の strip フォールバック。"""

    def test_around_strip(self) -> None:
        """``'"拠点"'`` のように quote ごと渡されても解決できるよう、
        normalize 段階で剥がす。"""
        candidates = _normalize_label_candidates('"拠点"')
        assert "拠点" in candidates, "quote 剥がしの候補がない"

    def test_includes_quote(self) -> None:
        """既存挙動を壊さない: quote なしの入力は素通り。"""
        candidates = _normalize_label_candidates("拠点")
        assert "拠点" in candidates


class TestResolverFallsBackToEdgeName:
    """LLM が edge 名 (connection_name) を渡しても spot に解決される。"""

    def _build_context(self) -> ToolRuntimeContextDto:
        result = SpotGraphUiContextBuilder().build(
            "現在地: 浜辺", _make_dto(_snap_two_edges())
        )
        return result.tool_runtime_context

    def test_edge_destination_spot_resolve(self) -> None:
        """LLM が ``destination_label='浜辺の砂道'`` (= edge 名) を渡しても、
        その接続先 spot ``拠点`` (spot_id=2) に解決される。silent rescue。"""
        ctx = self._build_context()
        target = resolve_destination_target("浜辺の砂道", ctx)
        assert target.spot_id == 2, (
            "edge 名 fallback が機能していない。LLM の typical な誤りを救えない"
        )

    def test_spot_resolve(self) -> None:
        """既存挙動を壊さない。"""
        ctx = self._build_context()
        target = resolve_destination_target("拠点", ctx)
        assert target.spot_id == 2

    def test_quote_per_spot_resolve(self) -> None:
        """``destination_label='"拠点"'`` のように LLM が quote ごと渡しても OK。"""
        ctx = self._build_context()
        target = resolve_destination_target('"拠点"', ctx)
        assert target.spot_id == 2


class TestShadowEntriesAreHiddenFromListing:
    """``list_destination_labels`` が shadow 候補を表示しない。"""

    def test_candidate_column_edge(self) -> None:
        """error message での候補一覧には spot 名だけが出る。edge 名は
        内部の fallback 用なのでユーザに見せない (混乱を避ける)。"""
        result = SpotGraphUiContextBuilder().build(
            "現在地: 浜辺", _make_dto(_snap_two_edges())
        )
        listing = list_destination_labels(result.tool_runtime_context.targets)
        assert "浜辺の砂道" not in listing, (
            "edge 名は内部 shadow なので候補一覧に出さない"
        )
        assert "森への入口" not in listing
        assert "拠点" in listing, "正規の候補 (spot 名) は出ること"
        assert "森の入口" in listing
