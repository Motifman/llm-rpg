"""PR 6 (#404 後続) ラベル → 名前+ordinal リファクタの回帰テスト。

prompt 上から ``S1`` / ``OBJ1`` / ``SL1`` / ``P1`` / ``M1`` / ``I1`` / ``G1`` の
ような揮発的ラベル prefix を撤去し、名前直書き + 同名衝突時 ``#N`` ordinal で
disambiguation する仕様に倒した。

ラベル設計を捨てた理由 (実験 #29 OFF 分析の feedback):
- 揮発性: 同じ ``I2`` が次 turn で別アイテムを指す
- 記憶汚染: memo や episodic に ``I2 を渡した`` と書かれても再構築できない
- 名前直書きなら過去 turn のメモがそのまま意味を持つ

テスト対象:
1. ``_build_ordinal_disambiguator`` 単体: 同名衝突に ``#1`` / ``#2`` を付与
2. UiContextBuilder の各 section: 旧ラベル prefix を出さず名前直書き
3. 内部 collector は引き続き旧 label key で target を保持 (resolver 互換)
4. collector の display_name は disambiguated 名 (resolver が name で解決可)
"""

from __future__ import annotations

from ai_rpg_world.application.llm.services.spot_graph_ui_context_builder import (
    SpotGraphUiContextBuilder,
    _build_ordinal_disambiguator,
)
from ai_rpg_world.application.world_graph.spot_graph_current_state_dtos import (
    SpotGraphConnectionEntry,
    SpotGraphGroundItemEntry,
    SpotGraphInventoryItemEntry,
    SpotGraphMonsterEntry,
    SpotGraphNearbyEntityEntry,
    SpotGraphPlayerSnapshotDto,
)
from ai_rpg_world.application.world.contracts.dtos import (
    AttentionLevel,
    PlayerCurrentStateDto,
)


class TestOrdinalDisambiguator:
    """``_build_ordinal_disambiguator`` の境界条件。"""

    def test_returns_all_name(self) -> None:
        """全部一意なら 素の名前を返す。"""
        result = _build_ordinal_disambiguator(["A", "B", "C"])
        assert result == {0: "A", 1: "B", 2: "C"}

    def test_documented_behavior(self) -> None:
        """A は単独 → "A"、B は 2 つ → "B #1" / "B #2"。"""
        result = _build_ordinal_disambiguator(["A", "B", "B"])
        assert result == {0: "A", 1: "B #1", 2: "B #2"}

    def test_three_one_two_three(self) -> None:
        """3 重衝突は 1 2 3。"""
        result = _build_ordinal_disambiguator(["X", "X", "X"])
        assert result == {0: "X #1", 1: "X #2", 2: "X #3"}

    def test_ordinal(self) -> None:
        """並び順で #1 → #2。後から見た方が #1 にならない。"""
        result = _build_ordinal_disambiguator(["A", "B", "A", "B", "A"])
        assert result == {
            0: "A #1", 1: "B #1", 2: "A #2", 3: "B #2", 4: "A #3",
        }

    def test_empty_dict(self) -> None:
        """空入力なら 空辞書。"""
        assert _build_ordinal_disambiguator([]) == {}

    def test_includes_name_base_ordinal(self) -> None:
        """PR #421 MEDIUM 反映: シナリオ JSON が "小屋 #1" のような名前を
        既に持っているとき、衝突検出は base name (= "#N" を剥がしたもの) で
        行い、"小屋 #1 #1" のような二重 ordinal を生まない。

        2 つの "小屋 #1" 入力 → 出力は "小屋 #1" / "小屋 #2"。
        """
        result = _build_ordinal_disambiguator(["小屋 #1", "小屋 #2"])
        # 入力 2 件はいずれも base="小屋"、counts["小屋"]=2 で disambiguate
        assert result == {0: "小屋 #1", 1: "小屋 #2"}

    def test_existing_ordinal_name(self) -> None:
        """既存 ordinal と素の名前が混ざるケース。"""
        result = _build_ordinal_disambiguator(["小屋", "小屋 #2"])
        # 両方 base="小屋"、衝突するので index 順で renumber される
        assert result == {0: "小屋 #1", 1: "小屋 #2"}

    def test_public_different_import(self) -> None:
        """PR #421 LOW 反映: ``build_ordinal_disambiguator`` (private prefix 無し)
        を public 関数として export。private alias は後方互換のために残す。"""
        from ai_rpg_world.application.llm.services.spot_graph_ui_context_builder import (
            build_ordinal_disambiguator,
        )
        assert build_ordinal_disambiguator is _build_ordinal_disambiguator
        # public 名で呼んでも動作する
        assert build_ordinal_disambiguator(["A", "A"]) == {0: "A #1", 1: "A #2"}


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


def _make_snap(**overrides) -> SpotGraphPlayerSnapshotDto:
    defaults: dict = {
        "current_spot_id": 1,
        "current_spot_name": "テスト",
        "current_spot_description": "",
        "travel_status_line": None,
    }
    defaults.update(overrides)
    return SpotGraphPlayerSnapshotDto(**defaults)


def _build(snap: SpotGraphPlayerSnapshotDto) -> str:
    dto = _make_dto(snap)
    result = SpotGraphUiContextBuilder().build("base", dto)
    return result.current_state_text


class TestSectionRenderingHasNoLabelPrefix:
    """各 section が旧ラベル prefix を出さないことを確認。"""

    def test_inventory_section_i1_prefix(self) -> None:
        """inventorysection に I1prefix が無い。"""
        snap = _make_snap(
            inventory_items=(
                SpotGraphInventoryItemEntry(item_spec_id=1, name="流木", quantity=2),
            ),
        )
        text = _build(snap)
        # PR (use_item quoted): item 名は ``""`` で囲んで表示する規約
        assert '- "流木"' in text
        assert "I1:" not in text
        assert "I1 " not in text  # 安全側でスペースも検査

    def test_ground_items_section_g1_prefix(self) -> None:
        """grounditemssection に G1prefix が無い。"""
        snap = _make_snap(
            ground_items=(
                SpotGraphGroundItemEntry(item_instance_id=1, item_spec_id=1, name="流木"),
            ),
        )
        text = _build(snap)
        # PR (use_item quoted): ground item 名は ``""`` で囲んで表示する
        assert '- "流木"' in text
        assert "G1:" not in text


class TestSectionRenderingHasOrdinalDisambiguation:
    """同名衝突時に ``#1`` / ``#2`` が付くことを確認。"""

    def test_inventory_two(self) -> None:
        """同じ name のアイテムが (例えば spoiled/fresh 別エントリで) 並ぶケース。"""
        snap = _make_snap(
            inventory_items=(
                SpotGraphInventoryItemEntry(item_spec_id=1, name="生の魚", quantity=1),
                SpotGraphInventoryItemEntry(
                    item_spec_id=1, name="生の魚", quantity=1, is_spoiled=True,
                ),
            ),
        )
        text = _build(snap)
        assert "生の魚 #1" in text
        assert "生の魚 #2" in text

    def test_monster_two(self) -> None:
        """monster に同種 2 体ならば番号が付く。"""
        snap = _make_snap(
            monsters_at_spot=(
                SpotGraphMonsterEntry(
                    monster_id=1, display_name="灰色のオオカミ",
                    behavior_label="落ち着いている", health_bucket="healthy",
                ),
                SpotGraphMonsterEntry(
                    monster_id=2, display_name="灰色のオオカミ",
                    behavior_label="こちらを追っている", health_bucket="dying",
                ),
            ),
        )
        text = _build(snap)
        assert "灰色のオオカミ #1" in text
        assert "灰色のオオカミ #2" in text

    def test_player_two(self) -> None:
        """scenario で同名 player が居たら #N で区別する (防御的)。"""
        snap = _make_snap(
            nearby_entities=(
                SpotGraphNearbyEntityEntry(entity_id=2, display_name="ノア"),
                SpotGraphNearbyEntityEntry(entity_id=3, display_name="ノア"),
            ),
        )
        text = _build(snap)
        assert "ノア #1" in text
        assert "ノア #2" in text


class TestCollectorPreservesLabelKey:
    """内部 collector は引き続き label をキーに target を保存する (resolver 互換)。"""

    def test_inventory_collector_key_i1_label(self) -> None:
        """inventory collector key は I1 等のラベルのまま。"""
        snap = _make_snap(
            inventory_items=(
                SpotGraphInventoryItemEntry(item_spec_id=1, name="流木", quantity=1),
            ),
        )
        dto = _make_dto(snap)
        result = SpotGraphUiContextBuilder().build("base", dto)
        targets = result.tool_runtime_context.targets
        # 内部 key は label
        assert "I1" in targets
        # display_name は disambiguated 名 (この場合 衝突なしで "流木")
        assert targets["I1"].display_name == "流木"

    def test_target_display_name_disambiguated(self) -> None:
        """resolver が ``灰色のオオカミ #2`` を渡されたら 2 番目に解決できるよう、
        target.display_name には ordinal 付きの名前を保存する。"""
        snap = _make_snap(
            monsters_at_spot=(
                SpotGraphMonsterEntry(
                    monster_id=10, display_name="灰色のオオカミ",
                    behavior_label="落ち着いている", health_bucket="healthy",
                ),
                SpotGraphMonsterEntry(
                    monster_id=11, display_name="灰色のオオカミ",
                    behavior_label="こちらを追っている", health_bucket="dying",
                ),
            ),
        )
        dto = _make_dto(snap)
        result = SpotGraphUiContextBuilder().build("base", dto)
        targets = result.tool_runtime_context.targets
        assert targets["M1"].display_name == "灰色のオオカミ #1"
        assert targets["M2"].display_name == "灰色のオオカミ #2"
        # monster_id はそのまま (= 物理的に別個体)
        assert targets["M1"].monster_id == 10
        assert targets["M2"].monster_id == 11
