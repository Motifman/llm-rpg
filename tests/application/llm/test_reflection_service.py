"""RuleBasedReflectionService のテスト（正常・境界・例外）"""

import pytest
from datetime import datetime, timedelta

from ai_rpg_world.application.llm.contracts.dtos import EpisodeMemoryEntry
from ai_rpg_world.application.llm.services.in_memory_episode_memory_store import (
    InMemoryEpisodeMemoryStore,
)
from ai_rpg_world.application.llm.services.in_memory_long_term_memory_store import (
    InMemoryLongTermMemoryStore,
)
from ai_rpg_world.application.llm.services.reflection_service import (
    RuleBasedReflectionService,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


def _make_episode(eid: str, ts: datetime | None = None) -> EpisodeMemoryEntry:
    return EpisodeMemoryEntry(
        id=eid,
        context_summary="洞窟でチェストを発見",
        action_taken="open_chest を実行",
        outcome_summary="回復ポーションを入手",
        entity_ids=("chest_1",),
        location_id=None,
        timestamp=ts or datetime.now(),
        importance="medium",
        surprise=False,
        recall_count=2,
    )


class TestRuleBasedReflectionService:
    """RuleBasedReflectionService の正常・境界・例外ケース"""

    @pytest.fixture
    def episode_store(self):
        return InMemoryEpisodeMemoryStore()

    @pytest.fixture
    def long_term_store(self):
        return InMemoryLongTermMemoryStore()

    @pytest.fixture
    def service(self, episode_store, long_term_store):
        return RuleBasedReflectionService(
            episode_store=episode_store,
            long_term_store=long_term_store,
        )

    @pytest.fixture
    def player_id(self):
        return PlayerId(1)

    def test_run_adds_facts_and_laws_from_episodes(
        self, service, episode_store, long_term_store, player_id
    ):
        """run で重要エピソードから事実と法則が長期記憶に追加される"""
        since = datetime.now() - timedelta(days=1)
        episode_store.add(player_id, _make_episode("e1", ts=datetime.now()))
        service.run(player_id, since=since, episode_limit=10)
        facts = long_term_store.search_facts(player_id, limit=10)
        laws = long_term_store.find_laws(player_id, limit=10)
        assert len(facts) >= 1
        assert "洞窟" in facts[0].content or "チェスト" in facts[0].content
        assert len(laws) >= 1
        assert "open_chest" in laws[0].subject or "回復" in laws[0].target

    def test_run_with_no_episodes_does_not_raise(
        self, service, player_id
    ):
        """since 以降にエピソードが無くても run は正常終了する"""
        since = datetime.now() + timedelta(days=1)
        service.run(player_id, since=since, episode_limit=10)

    def test_run_player_id_none_raises_type_error(self, service):
        """player_id が None のとき TypeError"""
        with pytest.raises(TypeError, match="player_id must be PlayerId"):
            service.run(
                None,  # type: ignore[arg-type]
                since=datetime.now(),
            )

    def test_run_since_not_datetime_raises_type_error(self, service, player_id):
        """since が datetime でないとき TypeError"""
        with pytest.raises(TypeError, match="since must be datetime"):
            service.run(
                player_id,
                since="invalid",  # type: ignore[arg-type]
            )

    def test_run_negative_episode_limit_raises_value_error(
        self, service, player_id
    ):
        """episode_limit が負のとき ValueError"""
        with pytest.raises(ValueError, match="episode_limit must be 0 or greater"):
            service.run(
                player_id,
                since=datetime.now() - timedelta(days=1),
                episode_limit=-1,
            )

    def test_run_invalid_min_importance_raises_value_error(
        self, service, episode_store, player_id
    ):
        """min_importance が low/medium/high 以外のとき ValueError（ストア経由で伝播）"""
        since = datetime.now() - timedelta(days=1)
        episode_store.add(player_id, _make_episode("e1", ts=datetime.now()))
        with pytest.raises(ValueError, match="min_importance must be 'low', 'medium', or 'high'"):
            service.run(
                player_id,
                since=since,
                min_importance="invalid",
                episode_limit=10,
            )

    def test_init_episode_store_not_interface_raises_type_error(
        self, long_term_store
    ):
        """episode_store が IEpisodeMemoryStore でないとき TypeError"""
        with pytest.raises(
            TypeError, match="episode_store must be IEpisodeMemoryStore"
        ):
            RuleBasedReflectionService(
                episode_store=None,  # type: ignore[arg-type]
                long_term_store=long_term_store,
            )

    def test_init_long_term_store_not_interface_raises_type_error(
        self, episode_store
    ):
        """long_term_store が ILongTermMemoryStore でないとき TypeError"""
        with pytest.raises(
            TypeError, match="long_term_store must be ILongTermMemoryStore"
        ):
            RuleBasedReflectionService(
                episode_store=episode_store,
                long_term_store=None,  # type: ignore[arg-type]
            )
