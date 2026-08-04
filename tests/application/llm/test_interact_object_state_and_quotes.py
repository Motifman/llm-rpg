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
from ai_rpg_world.domain.world_graph.entity.spot_object import VISIBLE_STATE_TAGS_KEY


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
    """object 名の quote と、意味ラベルつき action 表示を保証する。"""

    def test_object_quote(self) -> None:
        """object 名が quote で囲まれる。"""
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

    def test_object_without_actions_is_visible_but_not_an_interact_target(self) -> None:
        """操作が 0 件の物体は情景には残すが、interact の選択肢には登録しない。"""
        snap = SpotGraphPlayerSnapshotDto(
            current_spot_id=1,
            current_spot_name="中央管制室",
            current_spot_description="",
            travel_status_line=None,
            objects=(
                SpotGraphObjectEntry(
                    object_id=10,
                    name="棚卸し帳",
                    description="古い記録が並んでいる。",
                    interactions=(),
                ),
            ),
        )

        result = SpotGraphUiContextBuilder().build("base", _make_dto(snap))

        assert '"棚卸し帳"' in result.current_state_text
        assert "(なし)" not in result.current_state_text
        assert not any(
            target.kind == "spot_graph_object"
            and target.world_object_id == 10
            for target in result.tool_runtime_context.targets.values()
        )

    def test_action_name(self) -> None:
        """action は日本語の意味と tool に渡す識別子を対にして表示する。"""
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
        assert "[採取する (gather), 調べる (examine)]" in text, (
            "action 一覧に display_label と action_name の対応が出ていない"
        )
        # 旧 (action_name="gather") 冗長表記が消えている
        assert 'action_name="gather"' not in text
        assert 'action_name="examine"' not in text

    def test_action_condition_hints(self) -> None:
        """時刻・天候の前提条件ヒントは action_name に短く添えて表示する。"""
        snap = SpotGraphPlayerSnapshotDto(
            current_spot_id=1,
            current_spot_name="岩礁",
            current_spot_description="",
            travel_status_line=None,
            objects=(
                SpotGraphObjectEntry(
                    object_id=10,
                    name="沖の釣り場",
                    description="",
                    interactions=(
                        SpotGraphInteractionEntry(
                            action_name="fish_deep",
                            display_label="沖で釣りをする",
                            condition_hints=("夜不可", "嵐不可"),
                        ),
                    ),
                ),
            ),
        )
        result = SpotGraphUiContextBuilder().build("base", _make_dto(snap))
        text = result.current_state_text
        assert '[沖で釣りをする (fish_deep・夜不可・嵐不可)]' in text
        assert "fish_deep(夜不可" not in text
        assert result.tool_runtime_context.targets["OBJ1"].available_interactions == (
            "fish_deep",
        )
        assert all(
            "夜不可" not in action and "嵐不可" not in action
            for action in result.tool_runtime_context.targets[
                "OBJ1"
            ].available_interactions
        )

    def test_required_interaction_parameter_hint(self) -> None:
        """必須入力は意味ラベル・action_name と同じ括弧内に中黒で表示する。"""
        snap = SpotGraphPlayerSnapshotDto(
            current_spot_id=1,
            current_spot_name="浜辺の野営地",
            current_spot_description="",
            travel_status_line=None,
            objects=(
                SpotGraphObjectEntry(
                    object_id=10,
                    name="板切れの掲示",
                    description="伝言を書き残せる。",
                    interactions=(
                        SpotGraphInteractionEntry(
                            action_name="write_notice",
                            display_label="板切れに書き残す",
                            condition_hints=("text が要る",),
                        ),
                        SpotGraphInteractionEntry(
                            action_name="read_notice",
                            display_label="板切れを読む",
                        ),
                    ),
                ),
            ),
        )

        result = SpotGraphUiContextBuilder().build("base", _make_dto(snap))

        assert (
            '[板切れに書き残す (write_notice・text が要る), '
            '板切れを読む (read_notice)]' in result.current_state_text
        )
        assert result.tool_runtime_context.targets["OBJ1"].available_interactions == (
            "write_notice",
            "read_notice",
        )

    def test_failed_object_state_condition_hint_is_prompt_only(self) -> None:
        """OBJECT_STATE 失敗理由は「いまできない」行に出し、tool 候補は action_name のまま残る。"""
        snap = SpotGraphPlayerSnapshotDto(
            current_spot_id=1,
            current_spot_name="船倉",
            current_spot_description="",
            travel_status_line=None,
            objects=(
                SpotGraphObjectEntry(
                    object_id=10,
                    name="古い箱",
                    description="ふたの開いた箱。",
                    interactions=(
                        SpotGraphInteractionEntry(
                            action_name="open_chest",
                            display_label="箱を開ける",
                            blocking_hints=("箱はすでに空っぽだ。",),
                        ),
                        SpotGraphInteractionEntry(
                            action_name="examine",
                            display_label="調べる",
                        ),
                    ),
                ),
            ),
        )
        result = SpotGraphUiContextBuilder().build("base", _make_dto(snap))

        assert (
            '"古い箱" — ふたの開いた箱。 [調べる (examine)]'
            in result.current_state_text
        )
        assert (
            "      いまできない: 箱を開ける "
            "(open_chest・箱はすでに空っぽだ。)"
            in result.current_state_text
        )
        assert result.tool_runtime_context.targets["OBJ1"].available_interactions == (
            "open_chest",
            "examine",
        )
        assert all(
            "箱はすでに空っぽ" not in action
            for action in result.tool_runtime_context.targets[
                "OBJ1"
            ].available_interactions
        )

    def test_failed_object_stock_condition_hint_is_prompt_only(self) -> None:
        """OBJECT_STOCK_AT_LEAST 失敗理由は選べる行動欄から分けて表示する。"""
        snap = SpotGraphPlayerSnapshotDto(
            current_spot_id=1,
            current_spot_name="干潟",
            current_spot_description="",
            travel_status_line=None,
            objects=(
                SpotGraphObjectEntry(
                    object_id=10,
                    name="貝の干潟",
                    description="貝を採れる場所。",
                    interactions=(
                        SpotGraphInteractionEntry(
                            action_name="gather_shellfish",
                            display_label="貝を採る",
                            blocking_hints=("貝は採り尽くした。時間が経てば戻る。",),
                        ),
                    ),
                ),
            ),
        )
        result = SpotGraphUiContextBuilder().build("base", _make_dto(snap))

        assert (
            "いまできない: 貝を採る "
            "(gather_shellfish・貝は採り尽くした。時間が経てば戻る。)"
            in result.current_state_text
        )
        assert "[gather_shellfish" not in result.current_state_text
        assert result.tool_runtime_context.targets["OBJ1"].available_interactions == (
            "gather_shellfish",
        )
        assert all(
            "貝は採り尽くした" not in action
            for action in result.tool_runtime_context.targets[
                "OBJ1"
            ].available_interactions
        )

    def test_action_with_condition_and_blocking_hints_is_rendered_as_blocked(self) -> None:
        """宣言由来制約と現在の失敗理由を両方持つ action は、いまできない側にだけ出す。"""
        snap = SpotGraphPlayerSnapshotDto(
            current_spot_id=1,
            current_spot_name="小屋",
            current_spot_description="",
            travel_status_line=None,
            objects=(
                SpotGraphObjectEntry(
                    object_id=10,
                    name="崩れた梁",
                    description="太い梁が斜めに崩れている。",
                    interactions=(
                        SpotGraphInteractionEntry(
                            action_name="search",
                            display_label="棚を探す",
                            condition_hints=("夜不可",),
                            blocking_hints=("棚を調べた後",),
                        ),
                        SpotGraphInteractionEntry(
                            action_name="examine",
                            display_label="調べる",
                        ),
                    ),
                ),
            ),
        )
        result = SpotGraphUiContextBuilder().build("base", _make_dto(snap))

        assert (
            '"崩れた梁" — 太い梁が斜めに崩れている。 [調べる (examine)]'
            in result.current_state_text
        )
        assert (
            "      いまできない: 棚を探す (search・棚を調べた後)"
            in result.current_state_text
        )
        assert "search(夜不可" not in result.current_state_text
        assert result.tool_runtime_context.targets["OBJ1"].available_interactions == (
            "search",
            "examine",
        )

    def test_all_blocked_actions_do_not_render_empty_brackets(self) -> None:
        """全 action がいまできない側に回るとき、空の `[]` は表示しない。"""
        snap = SpotGraphPlayerSnapshotDto(
            current_spot_id=1,
            current_spot_name="小屋",
            current_spot_description="",
            travel_status_line=None,
            objects=(
                SpotGraphObjectEntry(
                    object_id=10,
                    name="崩れた梁",
                    description="太い梁が斜めに崩れている。",
                    interactions=(
                        SpotGraphInteractionEntry(
                            action_name="search",
                            display_label="棚を探す",
                            blocking_hints=("棚を調べた後",),
                        ),
                    ),
                ),
            ),
        )
        text = _build(snap)

        assert '"崩れた梁" — 太い梁が斜めに崩れている。' in text
        assert "[]" not in text
        assert "[ ]" not in text
        assert "      いまできない: 棚を探す (search・棚を調べた後)" in text

    def test_no_blocked_actions_do_not_render_blocked_line(self) -> None:
        """いまできない action が無ければ、追加行自体を出さない。"""
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
                        SpotGraphInteractionEntry(
                            action_name="gather",
                            display_label="拾う",
                        ),
                    ),
                ),
            ),
        )
        text = _build(snap)

        assert "[拾う (gather)]" in text
        assert "いまできない:" not in text

    def test_empty_display_label_falls_back_to_action_name(self) -> None:
        """display_label が空でも、表示側は落ちず action_name を候補に残す。"""
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
                        SpotGraphInteractionEntry(
                            action_name="gather_driftwood",
                            display_label="",
                        ),
                    ),
                ),
            ),
        )

        text = _build(snap)

        assert "[gather_driftwood]" in text

    def test_action(self) -> None:
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

    def test_state_empty_state_displayed(self) -> None:
        """available=false 由来のヒントは key=value でなく裸のタグとして表示される。"""
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
                    state={VISIBLE_STATE_TAGS_KEY: ("今は採れない・時間を置けば戻る",)},
                ),
            ),
        )
        text = _build(snap)
        assert '"東の茂み" (今は採れない・時間を置けば戻る)' in text
        assert "available" not in text
        assert "状態=" not in text
        assert "((今は採れない・時間を置けば戻る))" not in text

    def test_bare_hint_can_mix_with_key_value_state(self) -> None:
        """可用性ヒントは裸タグ、他の state は従来どおり key=value として同じ括弧内に並ぶ。"""
        snap = SpotGraphPlayerSnapshotDto(
            current_spot_id=1,
            current_spot_name="泉",
            current_spot_description="",
            travel_status_line=None,
            objects=(
                SpotGraphObjectEntry(
                    object_id=10,
                    name="湧水の口",
                    description="",
                    interactions=(
                        SpotGraphInteractionEntry(
                            action_name="drink_water", display_label="水を汲む"
                        ),
                    ),
                    state={
                        VISIBLE_STATE_TAGS_KEY: ("今は汲めない・時間を置けば戻る",),
                        "opened": True,
                    },
                ),
            ),
        )
        text = _build(snap)
        assert '"湧水の口" (今は汲めない・時間を置けば戻る, opened=true)' in text
        assert "状態=" not in text
        assert "((今は汲めない・時間を置けば戻る" not in text

    def test_state_empty_not_displayed(self) -> None:
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

    def test_sub_location_quote(self) -> None:
        """sub location 名が quote で囲まれる。"""
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

    def test_other_player_quote(self) -> None:
        """他プレイヤー名が quote で囲まれる。"""
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

    def test_monster_quote(self) -> None:
        """モンスター名が quote で囲まれる。"""
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

    def test_quote_per_sub_location_resolve(self) -> None:
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

    def test_quote_resolve(self) -> None:
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

    def test_state_value_none_null_displayed(self) -> None:
        """state 値が None の場合 null で表示される。"""
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

    def test_legacy_spot_state_block(self) -> None:
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
    """INTERACT_DEFINITION の target_label description が quote 規約に触れる。"""

    def test_target_label_description_included(self) -> None:
        """objectlabeldescription にクオート規約が含まれる。"""
        desc = INTERACT_DEFINITION.parameters["properties"]["target_label"][
            "description"
        ]
        assert "\"" in desc
        assert (
            "囲ま" in desc or "クオート" in desc or "ダブルクォート" in desc
        )

    def test_description_string(self) -> None:
        """description は静的文字列。"""
        desc = INTERACT_DEFINITION.parameters["properties"]["target_label"][
            "description"
        ]
        assert isinstance(desc, str)
        assert "{" not in desc
