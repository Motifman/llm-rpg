"""``WorldNounMatcher`` (Aho-Corasick + 正規化 + エイリアス) の単体テスト
(Issue #283 後続)。

検証する不変条件:
- 基本のマッチング (単一 / 複数 / 重複なし)
- Aho-Corasick の failure link が正しく動く (パターン同士の prefix / suffix 関係)
- NFKC 正規化 (全角→半角、合成文字)
- casefold (英字大文字小文字)
- エイリアス登録による別表記吸収
- カテゴリごとに正しい cue axis / value 形式で返る
- NullWorldNounMatcher は常に空
- 空入力・空パターンの edge case
"""

from __future__ import annotations

import pytest

from ai_rpg_world.application.llm.services.world_noun_matcher import (
    AhoCorasickWorldNounMatcher,
    IWorldNounMatcher,
    NounMatch,
    NullWorldNounMatcher,
    WorldNounMatcherBuilder,
)


class TestBasicMatching:
    """基本動作: 登録した名前を text 中から検出できる。"""

    def test_単一スポット名が_1_箇所マッチする(self) -> None:
        m = (
            WorldNounMatcherBuilder()
            .add_spot("書架A", spot_id=3)
            .build()
        )
        result = m.find_in_text("リン、書架A で待ってる")
        assert len(result) == 1
        assert result[0].axis == "place_spot"
        assert result[0].value == "3"
        assert result[0].matched_text == "書架A"

    def test_同じパターンが複数箇所に出現すれば全件返る(self) -> None:
        m = WorldNounMatcherBuilder().add_spot("書架A", spot_id=3).build()
        result = m.find_in_text("書架A も書架A も")
        # 2 箇所マッチする
        assert len(result) == 2
        assert all(r.value == "3" for r in result)
        # 順序は出現位置の昇順
        assert result[0].start < result[1].start

    def test_異なるカテゴリの名前が混在しても全件マッチ(self) -> None:
        m = (
            WorldNounMatcherBuilder()
            .add_spot("書架A", spot_id=3)
            .add_character("リン", player_id=2)
            .add_world_object("案内板", world_object_id=10)
            .build()
        )
        result = m.find_in_text("リンが書架A の案内板を見ている")
        cue_pairs = {(r.axis, r.value) for r in result}
        assert ("entity", "spot_graph_player_2") in cue_pairs
        assert ("place_spot", "3") in cue_pairs
        assert ("object", "world_object_10") in cue_pairs

    def test_登録されていない名前はマッチしない(self) -> None:
        m = WorldNounMatcherBuilder().add_spot("書架A", spot_id=3).build()
        result = m.find_in_text("書架B にいる")
        assert result == ()


class TestAhoCorasickFailureLink:
    """Aho-Corasick の failure link / output 統合が正しく動く。

    AC の本質は「現在 node でマッチしない文字が来たとき、長い suffix を
    保つ別 node に飛ぶ」こと。これが効くケースを試す。
    """

    def test_あるパターンが別パターンの_suffix_でもマッチする(self) -> None:
        """パターン ``[bc, abc]`` で text ``xabc`` を検索すると、a→b→c で
        終端 node ``abc`` に到達するが、その node の output には failure 経由で
        ``bc`` も含まれる必要がある。"""
        m = (
            WorldNounMatcherBuilder()
            .add_spot("bc", spot_id=1)
            .add_spot("abc", spot_id=2)
            .build()
        )
        result = m.find_in_text("xabc")
        cue_values = {r.value for r in result}
        assert "2" in cue_values  # abc
        assert "1" in cue_values  # bc (failure link 経由)

    def test_途中で別パターンに分岐できる(self) -> None:
        """``書架A`` と ``書庫`` を登録。``書架A も書庫も`` という text で
        両方検出される。"""
        m = (
            WorldNounMatcherBuilder()
            .add_spot("書架A", spot_id=3)
            .add_spot("書庫", spot_id=5)
            .build()
        )
        result = m.find_in_text("書架A も書庫も")
        values = {r.value for r in result}
        assert values == {"3", "5"}

    def test_長いパターンの中にある短いパターンも検出される(self) -> None:
        """``書架`` を登録、text ``書架A`` でもマッチする (substring match)。
        これは Aho-Corasick の語境界 unaware な挙動。シナリオ命名で
        ``書架`` と ``書架A`` を両方登録するなら両方マッチする (caller dedupe)。"""
        m = WorldNounMatcherBuilder().add_spot("書架", spot_id=99).build()
        result = m.find_in_text("リンは書架Aにいる")
        assert len(result) == 1
        assert result[0].value == "99"


class TestNormalization:
    """NFKC + casefold の正規化が効くこと。"""

    def test_全角アルファベットは半角と同じ扱い(self) -> None:
        """``書架Ａ`` (全角A) と ``書架A`` (半角A) が同一視される。"""
        m = WorldNounMatcherBuilder().add_spot("書架A", spot_id=3).build()
        result = m.find_in_text("書架Ａ で待ってる")  # 全角 A
        assert len(result) == 1
        assert result[0].value == "3"

    def test_英字の大文字小文字は同一視(self) -> None:
        m = WorldNounMatcherBuilder().add_spot("RoomA", spot_id=7).build()
        result = m.find_in_text("入った先は ROOMA だった")
        assert len(result) == 1
        assert result[0].value == "7"

    def test_全角数字は半角数字と同一視(self) -> None:
        m = WorldNounMatcherBuilder().add_spot("S3", spot_id=3).build()
        result = m.find_in_text("S３ へ移動")  # 全角 3
        assert len(result) == 1


class TestAliases:
    """エイリアス登録による別表記吸収。"""

    def test_エイリアスでも同じ_cue_value_が立つ(self) -> None:
        m = (
            WorldNounMatcherBuilder()
            .add_spot("書架A", spot_id=3, aliases=("第三書架", "古文書庫"))
            .build()
        )
        for text in ("書架A", "第三書架", "古文書庫"):
            result = m.find_in_text(text)
            assert len(result) == 1
            assert result[0].value == "3"
            # display は primary (= "書架A") に固定される
            assert result[0].matched_text in {"書架A", text}  # 元 text or primary

    def test_空エイリアスは無視される(self) -> None:
        """空文字 / 空白だけのエイリアスは登録されない (無限マッチ防止)。"""
        m = (
            WorldNounMatcherBuilder()
            .add_spot("書架A", spot_id=3, aliases=("", "   "))
            .build()
        )
        result = m.find_in_text("何もない")
        assert result == ()


class TestCueAxisValueFormat:
    """各 add_X メソッドが ``episodic_cue_rules`` 既存 cue と互換な
    (axis, value) を返す。"""

    def test_add_spot_は_place_spot_str_id_を返す(self) -> None:
        m = WorldNounMatcherBuilder().add_spot("X", spot_id=42).build()
        result = m.find_in_text("X")
        assert result[0].axis == "place_spot"
        assert result[0].value == "42"

    def test_add_character_は_entity_spot_graph_player_id_を返す(self) -> None:
        m = WorldNounMatcherBuilder().add_character("リン", player_id=2).build()
        result = m.find_in_text("リン")
        assert result[0].axis == "entity"
        assert result[0].value == "spot_graph_player_2"

    def test_add_world_object_は_object_world_object_id_を返す(self) -> None:
        m = WorldNounMatcherBuilder().add_world_object("案内板", world_object_id=10).build()
        result = m.find_in_text("案内板")
        assert result[0].axis == "object"
        assert result[0].value == "world_object_10"

    def test_add_item_は_object_item_instance_id_を返す(self) -> None:
        m = WorldNounMatcherBuilder().add_item("鍵", item_instance_id=100).build()
        result = m.find_in_text("鍵")
        assert result[0].axis == "object"
        assert result[0].value == "item_instance_100"


class TestNullMatcher:
    """NullWorldNounMatcher は常に空を返す (no-op safe default)。"""

    def test_空登録の_builder_は_null_matcher_を返す(self) -> None:
        m = WorldNounMatcherBuilder().build()
        assert isinstance(m, NullWorldNounMatcher)
        assert m.find_in_text("何でも") == ()

    def test_null_matcher_は_protocol_を満たす(self) -> None:
        m: IWorldNounMatcher = NullWorldNounMatcher()
        assert m.find_in_text("any") == ()


class TestEdgeCases:
    """境界ケース。"""

    def test_空_text_は_空タプル(self) -> None:
        m = WorldNounMatcherBuilder().add_spot("書架A", spot_id=3).build()
        assert m.find_in_text("") == ()

    def test_位置情報が_text_index_と整合(self) -> None:
        """同じ codepoint 長で正規化されるパターンなら start/end は元 text の
        index と一致する。"""
        m = WorldNounMatcherBuilder().add_spot("書架A", spot_id=3).build()
        text = "リン、書架A で待ってる"
        result = m.find_in_text(text)
        assert len(result) == 1
        # text[result[0].start:result[0].end] が "書架A" になる
        assert text[result[0].start : result[0].end] == "書架A"

    def test_NounMatch_の不変条件(self) -> None:
        """空 axis / 空 value / end <= start は ValueError。"""
        with pytest.raises(ValueError):
            NounMatch(axis="", value="x", matched_text="x", start=0, end=1)
        with pytest.raises(ValueError):
            NounMatch(axis="a", value="", matched_text="x", start=0, end=1)
        with pytest.raises(ValueError):
            NounMatch(axis="a", value="v", matched_text="x", start=0, end=0)


class TestProtocolConformance:
    """Aho-Corasick / Null の両方が ``IWorldNounMatcher`` Protocol を満たす。"""

    def test_aho_corasick_は_protocol_に準拠(self) -> None:
        m = WorldNounMatcherBuilder().add_spot("X", spot_id=1).build()
        assert isinstance(m, IWorldNounMatcher)

    def test_null_は_protocol_に準拠(self) -> None:
        m = NullWorldNounMatcher()
        assert isinstance(m, IWorldNounMatcher)
