"""interact / attack / whisper / tend_to_player / set_sub_location の
UI 可視性を向上させる (Y_after_pr639_640_200tick 後続、PR-EE + PR-FF + PR-X)。

Y_after_pr639_640 の分析で以下の 3 問題が判明:

1. **object 状態が prompt に露出しない (PR-X)**: `SpotGraphObjectEntry.state`
   は domain / DTO に存在するが、``_build_object_section`` が表示していない。
   結果 LLM は「もう漁り尽くした」茂み / 流木の山 に何度も gather を
   発火し PRECONDITION_FAILED を量産する (実測 13 件)。

2. **action 表示が冗長 (PR-EE)**: 現状 ``[gather(action_name="gather")]``
   のように「表示名 + action_name」の 2 重表記。LLM は action_name の
   quote 内をコピーする振る舞いが観察されるが、冗長で認知負荷が高い。
   ``[gather, examine]`` に簡略化する。

3. **quote 規約が object / player / monster / sub_location に未適用
   (PR-FF)**: PR #639/#640 で travel_to / use_item / drop_item など 6 tool
   に「``""`` 内が渡すべき値」規約を導入したが、残り 4 section (object
   / player / monster / sub_location) が quote されていない。全 tool
   横断規約に揃える。

3 変更をまとめて 1 PR にする理由: 同じ section を触るので cache 検証も
1 回で済む。動的セクション (object の state 変動を含む) だが、既存の
current_state セクション内で recent_events より上位ではないので cache
影響は限定的。
"""

from __future__ import annotations

from ai_rpg_world.application.llm.services.spot_graph_ui_context_builder import (
    SpotGraphUiContextBuilder,
)
from ai_rpg_world.application.llm.services.tool_catalog.spot_graph import (
    INTERACT_DEFINITION,
)
from ai_rpg_world.application.world.contracts.dtos import PlayerCurrentStateDto
from ai_rpg_world.application.world_graph.spot_graph_current_state_dtos import (
    SpotGraphInteractionEntry,
    SpotGraphMonsterEntry,
    SpotGraphNearbyEntityEntry,
    SpotGraphObjectEntry,
    SpotGraphPlayerSnapshotDto,
    SpotGraphSubLocationEntry,
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


def _build(snap: SpotGraphPlayerSnapshotDto) -> str:
    result = SpotGraphUiContextBuilder().build("base", _make_dto(snap))
    return result.current_state_text


class TestObjectSectionQuotesAndActionSimplification:
    """object 名の quote + action 表示簡略化 (PR-FF + PR-EE)。"""

    def test_object_名が_quote_で囲まれる(self) -> None:
        snap = SpotGraphPlayerSnapshotDto(
            current_spot_id=1,
            current_spot_name="浜辺",
            current_spot_description="",
            travel_status_line=None,
            objects=(
                SpotGraphObjectEntry(
                    object_id=10,
                    name="流木の山",
                    description="",
                    interactions=(
                        SpotGraphInteractionEntry(action_name="gather", display_label="採取する"),
                    ),
                ),
            ),
        )
        text = _build(snap)
        assert '"流木の山"' in text, "object 名が \"\" で囲まれていない"

    def test_action_表示は_action_name_だけの_カンマ区切り(self) -> None:
        """旧: ``[gather(action_name="gather") / examine(action_name="examine")]``
        新: ``[gather, examine]``。冗長表記を排除し「action_name の列」を
        直接示す。"""
        snap = SpotGraphPlayerSnapshotDto(
            current_spot_id=1,
            current_spot_name="浜辺",
            current_spot_description="",
            travel_status_line=None,
            objects=(
                SpotGraphObjectEntry(
                    object_id=10,
                    name="流木の山",
                    description="",
                    interactions=(
                        SpotGraphInteractionEntry(action_name="gather", display_label="採取する"),
                        SpotGraphInteractionEntry(action_name="examine", display_label="調べる"),
                    ),
                ),
            ),
        )
        text = _build(snap)
        assert "[gather, examine]" in text, (
            "action 一覧が action_name のカンマ区切り簡略表記になっていない"
        )
        # 旧 (action_name="gather") 冗長表記が消えている
        assert 'action_name="gather"' not in text
        assert 'action_name="examine"' not in text
        # 日本語 display_label はここでは出さない (LLM が action_name を渡す
        # ときに ambiguity を生まないため)
        assert "採取する" not in text
        assert "調べる" not in text

    def test_action_なしの_場合は_角括弧を省く(self) -> None:
        """interactions が空の object は ``[]`` や ``[-]`` を出さず、シンプル
        に名前+説明だけを表示する。"""
        snap = SpotGraphPlayerSnapshotDto(
            current_spot_id=1,
            current_spot_name="浜辺",
            current_spot_description="",
            travel_status_line=None,
            objects=(
                SpotGraphObjectEntry(
                    object_id=10,
                    name="石碑",
                    description="古びた石碑",
                    interactions=(),
                ),
            ),
        )
        text = _build(snap)
        assert '"石碑"' in text
        # 空 action で `[—]` のような無意味 tag を出さない
        assert "[—]" not in text and "[]" not in text


class TestObjectStateVisibleInPrompt:
    """object 状態を prompt に露出する (PR-X)。"""

    def test_state_が_空でない場合_状態タグが表示される(self) -> None:
        """`visible_state = {'available': False}` のような state が
        プロンプト上で ``(available=false)`` のように可視化される。
        LLM が「もう採れない」を prompt から直接読めるようになる。"""
        snap = SpotGraphPlayerSnapshotDto(
            current_spot_id=1,
            current_spot_name="ベリーの茂み",
            current_spot_description="",
            travel_status_line=None,
            objects=(
                SpotGraphObjectEntry(
                    object_id=10,
                    name="東の茂み",
                    description="",
                    interactions=(
                        SpotGraphInteractionEntry(
                            action_name="harvest_berry", display_label="採取"
                        ),
                    ),
                    state={"available": False},
                ),
            ),
        )
        text = _build(snap)
        # 状態タグが表示される
        assert "available" in text.lower() or "採取済み" in text or "使用不可" in text, (
            "state が空でないのに状態タグが表示されていない。LLM が"
            "「もう採れない」を prompt から読めない"
        )

    def test_state_が_空の場合_タグは表示されない(self) -> None:
        """state 空の object は既存挙動と同じでシンプル表示。"""
        snap = SpotGraphPlayerSnapshotDto(
            current_spot_id=1,
            current_spot_name="浜辺",
            current_spot_description="",
            travel_status_line=None,
            objects=(
                SpotGraphObjectEntry(
                    object_id=10,
                    name="石碑",
                    description="",
                    interactions=(
                        SpotGraphInteractionEntry(action_name="examine", display_label="調べる"),
                    ),
                    state={},
                ),
            ),
        )
        text = _build(snap)
        # 状態タグの空表示 () や (=) が付かない
        assert " ()" not in text
        assert "(=)" not in text


class TestSubLocationSectionQuotes:
    """sub_location 名が quote される (PR-FF)。"""

    def test_sub_location_名が_quote_で囲まれる(self) -> None:
        snap = SpotGraphPlayerSnapshotDto(
            current_spot_id=1,
            current_spot_name="祠",
            current_spot_description="",
            travel_status_line=None,
            sub_locations=(
                SpotGraphSubLocationEntry(
                    sub_location_id=5,
                    name="祭壇前",
                    is_current=True,
                    is_hidden=False,
                ),
            ),
        )
        text = _build(snap)
        assert '"祭壇前"' in text


class TestEntitySectionQuotes:
    """他プレイヤー名が quote される (PR-FF)。"""

    def test_他プレイヤー名が_quote_で囲まれる(self) -> None:
        snap = SpotGraphPlayerSnapshotDto(
            current_spot_id=1,
            current_spot_name="拠点",
            current_spot_description="",
            travel_status_line=None,
            nearby_entities=(
                SpotGraphNearbyEntityEntry(entity_id=2, display_name="ノア"),
            ),
        )
        text = _build(snap)
        assert '"ノア"' in text


class TestMonsterSectionQuotes:
    """モンスター名が quote される (PR-FF)。"""

    def test_モンスター名が_quote_で囲まれる(self) -> None:
        snap = SpotGraphPlayerSnapshotDto(
            current_spot_id=1,
            current_spot_name="森",
            current_spot_description="",
            travel_status_line=None,
            monsters_at_spot=(
                SpotGraphMonsterEntry(
                    monster_id=1,
                    display_name="灰色のオオカミ",
                    behavior_label="こちらを追っている",
                    health_bucket="healthy",
                ),
            ),
        )
        text = _build(snap)
        assert '"灰色のオオカミ"' in text


class TestSubLocationResolverStripsQuotes:
    """set_sub_location resolver が quote 込み入力を解決できる (regression:
    code-review CRITICAL、prompt 表示が ``"祭壇前"`` になったので resolver も
    quote strip を通す必要がある)。"""

    def test_quote_ごと_sub_location_名を_渡しても_resolve_される(self) -> None:
        """LLM が prompt 表示通り ``sub_location_label='"祭壇前"'`` と渡して
        きても解決できる。他 4 resolver (object/player/attack/tend) と同じく
        ``_normalize_label_candidates`` 経由で quote が剥がれる。"""
        from ai_rpg_world.application.llm.services._argument_resolvers.spot_graph_resolver import (
            resolve_sub_location_target,
        )
        from ai_rpg_world.application.llm.contracts.dtos import (
            ToolRuntimeContextDto,
            ToolRuntimeTargetDto,
        )
        ctx = ToolRuntimeContextDto(
            current_spot_id=1,
            current_sub_location_id=None,
            targets={
                "SL1": ToolRuntimeTargetDto(
                    label="SL1",
                    kind="spot_graph_sub_location",
                    display_name="祭壇前",
                    sub_location_id=42,
                ),
            },
        )
        # quote ごと渡す
        target = resolve_sub_location_target('"祭壇前"', ctx)
        assert target is not None
        assert target.sub_location_id == 42

    def test_quote_なし_の_場合も_従来通り_resolve_される(self) -> None:
        """後方互換: quote なし入力もこれまで通り動く。"""
        from ai_rpg_world.application.llm.services._argument_resolvers.spot_graph_resolver import (
            resolve_sub_location_target,
        )
        from ai_rpg_world.application.llm.contracts.dtos import (
            ToolRuntimeContextDto,
            ToolRuntimeTargetDto,
        )
        ctx = ToolRuntimeContextDto(
            current_spot_id=1,
            current_sub_location_id=None,
            targets={
                "SL1": ToolRuntimeTargetDto(
                    label="SL1",
                    kind="spot_graph_sub_location",
                    display_name="祭壇前",
                    sub_location_id=42,
                ),
            },
        )
        target = resolve_sub_location_target("祭壇前", ctx)
        assert target is not None
        assert target.sub_location_id == 42


class TestObjectStateNoneRendersAsNull:
    """state の値 None は ``null`` として表示される (regression: code-review
    MEDIUM、formatter._render_value と同じ convention)。"""

    def test_state_値が_None_の場合_null_で表示される(self) -> None:
        snap = SpotGraphPlayerSnapshotDto(
            current_spot_id=1,
            current_spot_name="祠",
            current_spot_description="",
            travel_status_line=None,
            objects=(
                SpotGraphObjectEntry(
                    object_id=10,
                    name="宝箱",
                    description="",
                    interactions=(
                        SpotGraphInteractionEntry(action_name="open", display_label="開ける"),
                    ),
                    state={"latch": None},
                ),
            ),
        )
        text = _build(snap)
        assert "latch=null" in text, (
            "None → null convention (formatter._render_value 由来) が保たれていない"
        )
        # Python の "None" 文字列は出さない
        assert "latch=None" not in text


class TestObjectStateNotDuplicatedInFormatter:
    """object state が formatter の別 section と inline で二重表示されない
    (regression: code-review HIGH)。"""

    def test_旧_スポット内オブジェクトの状態_block_は_削除済み(self) -> None:
        """PR-X 適用後、object state は「オブジェクト:」section の各行
        inline (``(key=value)``) にのみ表示される。formatter の旧
        「スポット内オブジェクトの状態:」block は削除された。"""
        snap = SpotGraphPlayerSnapshotDto(
            current_spot_id=1,
            current_spot_name="祠",
            current_spot_description="",
            travel_status_line=None,
            objects=(
                SpotGraphObjectEntry(
                    object_id=10,
                    name="燭台",
                    description="",
                    interactions=(
                        SpotGraphInteractionEntry(action_name="light", display_label="点火"),
                    ),
                    state={"lit": True},
                ),
            ),
        )
        # UiContextBuilder 経由でなく、formatter 単体でも旧 block が出ないことを確認
        from ai_rpg_world.application.llm.services.spot_graph_current_state_formatter import (
            SpotGraphCurrentStateFormatter,
        )
        text = SpotGraphCurrentStateFormatter().format(_make_dto(snap))
        assert "スポット内オブジェクトの状態:" not in text, (
            "旧 block が formatter に残っている。inline 版と重複してしまう"
        )


class TestInteractDescriptionMentionsQuoteRegime:
    """INTERACT_DEFINITION の object_label description が quote 規約に触れる。"""

    def test_object_label_description_に_クオート規約が含まれる(self) -> None:
        desc = INTERACT_DEFINITION.parameters["properties"]["object_label"][
            "description"
        ]
        assert "\"" in desc
        assert (
            "囲ま" in desc or "クオート" in desc or "ダブルクォート" in desc
        )

    def test_description_は_静的文字列(self) -> None:
        desc = INTERACT_DEFINITION.parameters["properties"]["object_label"][
            "description"
        ]
        assert isinstance(desc, str)
        assert "{" not in desc
