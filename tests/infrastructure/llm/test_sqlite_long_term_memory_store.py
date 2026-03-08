"""SqliteLongTermMemoryStore のテスト（永続化）"""

import pytest

from ai_rpg_world.infrastructure.llm.sqlite_long_term_memory_store import (
    SqliteLongTermMemoryStore,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class TestSqliteLongTermMemoryStore:
    """SqliteLongTermMemoryStore の永続化テスト"""

    def test_add_fact_and_search_persists_across_store_recreation(self, tmp_path):
        """add_fact した事実がストア再作成後も search_facts で取得できる"""
        db_path = tmp_path / "longterm.db"
        store = SqliteLongTermMemoryStore(db_path)
        player_id = PlayerId(1)
        store.add_fact(player_id, "洞窟の奥には強敵がいる")
        store.add_fact(player_id, "港町では魚が安い")

        store2 = SqliteLongTermMemoryStore(db_path)
        facts = store2.search_facts(player_id, limit=10)
        contents = [f.content for f in facts]
        assert "洞窟の奥には強敵がいる" in contents
        assert "港町では魚が安い" in contents

    def test_upsert_law_persists(self, tmp_path):
        """upsert_law した法則が永続化される"""
        db_path = tmp_path / "longterm.db"
        store = SqliteLongTermMemoryStore(db_path)
        player_id = PlayerId(1)
        store.upsert_law(player_id, subject="攻撃", relation="すると", target="ダメージ", delta_strength=1.0)

        store2 = SqliteLongTermMemoryStore(db_path)
        laws = store2.find_laws(player_id, limit=10)
        assert len(laws) >= 1
        subj_match = [l for l in laws if l.subject == "攻撃"]
        assert len(subj_match) >= 1
