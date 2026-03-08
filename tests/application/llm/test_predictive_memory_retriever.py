"""DefaultPredictiveMemoryRetriever のテスト（正常・境界・例外）"""

import pytest

from ai_rpg_world.application.llm.contracts.dtos import EpisodeMemoryEntry
from ai_rpg_world.application.llm.services.in_memory_episode_memory_store import (
    InMemoryEpisodeMemoryStore,
)
from ai_rpg_world.application.llm.services.in_memory_long_term_memory_store import (
    InMemoryLongTermMemoryStore,
)
from ai_rpg_world.application.llm.services.predictive_memory_retriever import (
    DefaultPredictiveMemoryRetriever,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


def _make_episode(
    eid: str,
    action: str = "move_to_destination",
    *,
    entity_ids: tuple[str, ...] = ("loc_1",),
    location_id: str | None = None,
    context_summary: str = "洞窟にいた",
) -> EpisodeMemoryEntry:
    from datetime import datetime
    return EpisodeMemoryEntry(
        id=eid,
        context_summary=context_summary,
        action_taken=action,
        outcome_summary="到着した",
        entity_ids=entity_ids,
        location_id=location_id,
        timestamp=datetime.now(),
        importance="medium",
        surprise=False,
        recall_count=0,
    )


class TestDefaultPredictiveMemoryRetriever:
    """DefaultPredictiveMemoryRetriever の正常・境界・例外ケース"""

    @pytest.fixture
    def episode_store(self):
        return InMemoryEpisodeMemoryStore()

    @pytest.fixture
    def long_term_store(self):
        return InMemoryLongTermMemoryStore()

    @pytest.fixture
    def retriever(self, episode_store, long_term_store):
        return DefaultPredictiveMemoryRetriever(
            episode_store=episode_store,
            long_term_store=long_term_store,
        )

    @pytest.fixture
    def player_id(self):
        return PlayerId(1)

    def test_retrieve_for_prediction_empty_stores_returns_nashi(
        self, retriever, player_id
    ):
        """記憶が無いとき「（なし）」を返す"""
        got = retriever.retrieve_for_prediction(
            player_id, "現在地: 洞窟", ["move_to_destination"]
        )
        assert got == "（なし）"

    def test_retrieve_for_prediction_returns_episodes_matching_action(
        self, retriever, episode_store, player_id
    ):
        """候補行動名に一致するエピソードが「過去の体験」に含まれる"""
        episode_store.add(
            player_id,
            _make_episode("e1", "move_to_destination を実行しました。"),
        )
        got = retriever.retrieve_for_prediction(
            player_id, "現在地: 洞窟", ["move_to_destination"]
        )
        assert "【過去の体験】" in got
        assert "洞窟にいた" in got
        assert "到着した" in got

    def test_retrieve_for_prediction_returns_episodes_matching_current_state_keywords(
        self, retriever, episode_store, player_id
    ):
        """現在状態のキーワードに一致するエピソードが候補行動に依存せず取得される"""
        episode_store.add(
            player_id,
            _make_episode(
                "e_state",
                action="observe",
                entity_ids=("洞窟入口", "老人"),
                location_id="洞窟入口",
                context_summary="洞窟入口で老人と会った",
            ),
        )

        got = retriever.retrieve_for_prediction(
            player_id,
            "現在地: 洞窟入口\n注目対象:\n  - 老人: 距離=1, 方角=南",
            ["world_no_op"],
        )

        assert "洞窟入口で老人と会った" in got

    def test_retrieve_for_prediction_increments_recall_count(
        self, retriever, episode_store, player_id
    ):
        """検索でヒットしたエピソードの recall_count が 1 増える"""
        episode_store.add(player_id, _make_episode("e1"))
        retriever.retrieve_for_prediction(
            player_id, "現在地: 洞窟", ["move_to_destination"]
        )
        recent = episode_store.get_recent(player_id, 1)
        assert len(recent) == 1
        assert recent[0].recall_count == 1

    def test_retrieve_for_prediction_includes_facts(
        self, retriever, long_term_store, player_id
    ):
        """長期記憶の事実が「覚えていること」に含まれる"""
        long_term_store.add_fact(player_id, "洞窟の奥には強敵がいる")
        got = retriever.retrieve_for_prediction(
            player_id, "現在地: 洞窟", []
        )
        assert "【覚えていること】" in got
        assert "強敵" in got

    def test_retrieve_for_prediction_filters_facts_by_current_state_keywords(
        self, retriever, long_term_store, player_id
    ):
        """現在状態キーワードに一致する事実を優先して取得する"""
        long_term_store.add_fact(player_id, "洞窟の奥には強敵がいる")
        long_term_store.add_fact(player_id, "港町では魚が安い")

        got = retriever.retrieve_for_prediction(
            player_id,
            "現在地: 洞窟",
            [],
        )

        assert "洞窟の奥には強敵がいる" in got
        assert "港町では魚が安い" not in got

    def test_retrieve_for_prediction_player_id_none_raises_type_error(
        self, retriever
    ):
        """player_id が None のとき TypeError"""
        with pytest.raises(TypeError, match="player_id must be PlayerId"):
            retriever.retrieve_for_prediction(
                None,  # type: ignore[arg-type]
                "現在地: 洞窟",
                ["move_to_destination"],
            )

    def test_retrieve_for_prediction_negative_episode_limit_raises_value_error(
        self, retriever, player_id
    ):
        """episode_limit が負のとき ValueError"""
        with pytest.raises(ValueError, match="episode_limit must be 0 or greater"):
            retriever.retrieve_for_prediction(
                player_id,
                "現在地: 洞窟",
                [],
                episode_limit=-1,
            )

    def test_retrieve_for_prediction_current_state_summary_not_str_raises_type_error(
        self, retriever, player_id
    ):
        """current_state_summary が str でないとき TypeError"""
        with pytest.raises(TypeError, match="current_state_summary must be str"):
            retriever.retrieve_for_prediction(
                player_id,
                123,  # type: ignore[arg-type]
                ["move_to_destination"],
            )

    def test_retrieve_for_prediction_candidate_action_names_not_list_raises_type_error(
        self, retriever, player_id
    ):
        """candidate_action_names が list でないとき TypeError"""
        with pytest.raises(TypeError, match="candidate_action_names must be list"):
            retriever.retrieve_for_prediction(
                player_id,
                "現在地: 洞窟",
                "move_to_destination",  # type: ignore[arg-type]
            )

    def test_retrieve_for_prediction_negative_fact_limit_raises_value_error(
        self, retriever, player_id
    ):
        """fact_limit が負のとき ValueError"""
        with pytest.raises(ValueError, match="fact_limit must be 0 or greater"):
            retriever.retrieve_for_prediction(
                player_id,
                "現在地: 洞窟",
                [],
                fact_limit=-1,
            )

    def test_retrieve_for_prediction_negative_law_limit_raises_value_error(
        self, retriever, player_id
    ):
        """law_limit が負のとき ValueError"""
        with pytest.raises(ValueError, match="law_limit must be 0 or greater"):
            retriever.retrieve_for_prediction(
                player_id,
                "現在地: 洞窟",
                [],
                law_limit=-1,
            )

    def test_init_episode_store_not_interface_raises_type_error(self, long_term_store):
        """episode_store が IEpisodeMemoryStore でないとき TypeError"""
        with pytest.raises(TypeError, match="episode_store must be IEpisodeMemoryStore"):
            DefaultPredictiveMemoryRetriever(
                episode_store=None,  # type: ignore[arg-type]
                long_term_store=long_term_store,
            )

    def test_init_long_term_store_not_interface_raises_type_error(self, episode_store):
        """long_term_store が ILongTermMemoryStore でないとき TypeError"""
        with pytest.raises(
            TypeError, match="long_term_store must be ILongTermMemoryStore"
        ):
            DefaultPredictiveMemoryRetriever(
                episode_store=episode_store,
                long_term_store=None,  # type: ignore[arg-type]
            )
