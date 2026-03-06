"""InMemoryLongTermMemoryStore のテスト（正常・境界・例外）"""

import pytest
from datetime import datetime

from ai_rpg_world.application.llm.services.in_memory_long_term_memory_store import (
    InMemoryLongTermMemoryStore,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class TestInMemoryLongTermMemoryStore:
    """InMemoryLongTermMemoryStore の正常・境界・例外ケース"""

    @pytest.fixture
    def store(self):
        return InMemoryLongTermMemoryStore()

    @pytest.fixture
    def player_id(self):
        return PlayerId(1)

    def test_add_fact_returns_id_and_search_finds_it(self, store, player_id):
        """add_fact で追加した事実が search_facts で取得できる"""
        fact_id = store.add_fact(player_id, "洞窟の奥には強敵がいる")
        assert isinstance(fact_id, str)
        assert len(fact_id) > 0
        got = store.search_facts(player_id, limit=10)
        assert len(got) == 1
        assert got[0].id == fact_id
        assert got[0].content == "洞窟の奥には強敵がいる"

    def test_search_facts_empty_for_unknown_player(self, store):
        """未登録プレイヤーでは search_facts が空リストを返す"""
        got = store.search_facts(PlayerId(999), limit=10)
        assert got == []

    def test_search_facts_keywords_filter(self, store, player_id):
        """keywords で事実をフィルタできる"""
        store.add_fact(player_id, "洞窟にはモンスターがいる")
        store.add_fact(player_id, "町には商人がいる")
        got = store.search_facts(player_id, keywords=["洞窟"], limit=10)
        assert len(got) == 1
        assert "洞窟" in got[0].content

    def test_upsert_law_adds_new_law(self, store, player_id):
        """upsert_law で新規法則が追加される"""
        store.upsert_law(player_id, "チェスト", "開けると_しばしば", "回復アイテム")
        got = store.find_laws(player_id, limit=10)
        assert len(got) == 1
        assert got[0].subject == "チェスト"
        assert got[0].target == "回復アイテム"
        assert got[0].strength == 1.0

    def test_upsert_law_same_key_increments_strength(self, store, player_id):
        """同一 (subject, relation, target) で upsert すると強度が加算される"""
        store.upsert_law(player_id, "チェスト", "開けると", "罠", delta_strength=1.0)
        store.upsert_law(player_id, "チェスト", "開けると", "罠", delta_strength=1.0)
        got = store.find_laws(player_id, limit=10)
        assert len(got) == 1
        assert got[0].strength == 2.0

    def test_find_laws_subject_filter(self, store, player_id):
        """find_laws の subject でフィルタできる"""
        store.upsert_law(player_id, "チェスト", "開けると", "回復")
        store.upsert_law(player_id, "NPC", "話すと", "クエスト")
        got = store.find_laws(player_id, subject="チェスト", limit=10)
        assert len(got) == 1
        assert got[0].subject == "チェスト"

    def test_find_laws_action_name_filter(self, store, player_id):
        """find_laws の action_name で relation を簡易検索できる"""
        store.upsert_law(player_id, "チェスト", "open_chest で開けると", "回復")
        got = store.find_laws(player_id, action_name="open_chest", limit=10)
        assert len(got) == 1

    def test_add_fact_player_id_none_raises_type_error(self, store):
        """add_fact に player_id が None のとき TypeError"""
        with pytest.raises(TypeError, match="player_id must be PlayerId"):
            store.add_fact(None, "content")  # type: ignore[arg-type]

    def test_add_fact_content_not_str_raises_type_error(self, store, player_id):
        """add_fact に content が str でないとき TypeError"""
        with pytest.raises(TypeError, match="content must be str"):
            store.add_fact(player_id, 123)  # type: ignore[arg-type]

    def test_search_facts_negative_limit_raises_value_error(self, store, player_id):
        """search_facts の limit が負で ValueError"""
        with pytest.raises(ValueError, match="limit must be 0 or greater"):
            store.search_facts(player_id, limit=-1)

    def test_upsert_law_player_id_none_raises_type_error(self, store):
        """upsert_law に player_id が None のとき TypeError"""
        with pytest.raises(TypeError, match="player_id must be PlayerId"):
            store.upsert_law(None, "s", "r", "t")  # type: ignore[arg-type]

    def test_upsert_law_subject_not_str_raises_type_error(self, store, player_id):
        """upsert_law に subject が str でないとき TypeError"""
        with pytest.raises(TypeError, match="subject must be str"):
            store.upsert_law(player_id, 123, "r", "t")  # type: ignore[arg-type]

    def test_find_laws_player_id_none_raises_type_error(self, store):
        """find_laws に player_id が None のとき TypeError"""
        with pytest.raises(TypeError, match="player_id must be PlayerId"):
            store.find_laws(None, limit=10)  # type: ignore[arg-type]
