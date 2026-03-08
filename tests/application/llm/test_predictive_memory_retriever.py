"""DefaultPredictiveMemoryRetriever のテスト（正常・境界・例外・ranking・DTO）"""

import pytest

from ai_rpg_world.application.llm.contracts.dtos import (
    EpisodeMemoryEntry,
    MemoryRetrievalQueryDto,
)
from ai_rpg_world.application.llm.services.in_memory_episode_memory_store import (
    InMemoryEpisodeMemoryStore,
)
from ai_rpg_world.application.llm.services.in_memory_long_term_memory_store import (
    InMemoryLongTermMemoryStore,
)
from ai_rpg_world.application.llm.services.predictive_memory_retriever import (
    DefaultPredictiveMemoryRetriever,
    build_memory_retrieval_query_from_state,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


def _make_episode(
    eid: str,
    action: str = "move_to_destination",
    *,
    entity_ids: tuple[str, ...] = ("loc_1",),
    location_id: str | None = None,
    context_summary: str = "洞窟にいた",
    world_object_ids: tuple[int, ...] = (),
    spot_id_value: int | None = None,
    scope_keys: tuple[str, ...] = (),
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
        world_object_ids=world_object_ids,
        spot_id_value=spot_id_value,
        scope_keys=scope_keys,
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

    def test_retrieve_with_query_dto_uses_entity_location_priority(
        self, retriever, episode_store, player_id
    ):
        """query_dto を渡したとき world_object_ids > spot_ids > entity > location > action の優先度で検索する"""
        episode_store.add(
            player_id,
            _make_episode(
                "e_entity",
                entity_ids=("老人",),
                location_id="洞窟入口",
                context_summary="洞窟入口で老人と会った",
            ),
        )
        episode_store.add(
            player_id,
            _make_episode(
                "e_loc",
                entity_ids=("別のNPC",),
                location_id="洞窟",
                context_summary="洞窟にいた",
            ),
        )
        q = MemoryRetrievalQueryDto(
            entity_ids=("老人",),
            location_ids=("洞窟",),
            action_names=("world_no_op",),
            free_text_keywords=(),
        )
        got = retriever.retrieve_for_prediction(
            player_id,
            "現在地: 洞窟",
            ["world_no_op"],
            query_dto=q,
        )
        assert "老人と会った" in got
        assert "洞窟にいた" in got

    def test_retrieve_dedupes_facts_by_content(
        self, retriever, long_term_store, player_id
    ):
        """事実の重複（同一 content）が除去される"""
        long_term_store.add_fact(player_id, "洞窟の奥には宝箱がある")
        long_term_store.add_fact(player_id, "洞窟の奥には宝箱がある")
        got = retriever.retrieve_for_prediction(
            player_id, "現在地: 洞窟", [], fact_limit=10
        )
        count = got.count("洞窟の奥には宝箱がある")
        assert count == 1

    def test_retrieve_with_world_object_ids_prioritizes_stable_id_match(
        self, retriever, episode_store, player_id
    ):
        """world_object_ids 検索で stable id が名前より優先される（同名別 object で stable id が勝つ）"""
        # 同じ display_name「老人」を持つ 2 件。wo_id=10 は「洞窟の老人」、wo_id=20 は「港町の老人」
        episode_store.add(
            player_id,
            _make_episode(
                "e_wo10",
                entity_ids=("老人",),
                location_id="洞窟",
                context_summary="洞窟の老人と話した",
                world_object_ids=(10,),
                spot_id_value=1,
            ),
        )
        episode_store.add(
            player_id,
            _make_episode(
                "e_wo20",
                entity_ids=("老人",),
                location_id="港町",
                context_summary="港町の老人と話した",
                world_object_ids=(20,),
                spot_id_value=2,
            ),
        )
        q = MemoryRetrievalQueryDto(
            entity_ids=("老人",),
            world_object_ids=(10,),
            spot_ids=(),
        )
        got = retriever.retrieve_for_prediction(
            player_id, "現在地: 洞窟", [], query_dto=q, episode_limit=1
        )
        # stable id ヒットが先に add_unique されるため、limit=1 なら洞窟の老人のみ
        assert "洞窟の老人と話した" in got
        assert "港町の老人と話した" not in got

    def test_build_query_includes_active_conversation_npc_id(
        self,
    ):
        """build_memory_retrieval_query_from_state は active_conversation の npc_world_object_id を world_object_ids に含める"""
        mock_dto = type("MockDto", (), {})()
        mock_dto.current_spot_id = 5
        mock_dto.current_spot_name = "広場"
        mock_dto.area_name = None
        mock_dto.connected_spot_ids = set()
        mock_dto.connected_spot_names = set()
        mock_dto.visible_objects = []
        mock_dto.notable_objects = []
        mock_dto.actionable_objects = []
        mock_dto.available_moves = []
        ac = type("MockAC", (), {"npc_world_object_id": 42})()
        mock_dto.active_conversation = ac
        q = build_memory_retrieval_query_from_state(
            mock_dto, ["talk_to"], current_state_summary=None
        )
        assert 42 in q.world_object_ids
        assert 5 in q.spot_ids

    def test_retrieve_with_spot_ids_returns_revisit_memory(
        self, retriever, episode_store, player_id
    ):
        """spot_ids だけで再訪記憶が引ける"""
        episode_store.add(
            player_id,
            _make_episode(
                "e_spot5",
                entity_ids=("広場",),
                location_id="広場",
                context_summary="広場でクエストを受けた",
                world_object_ids=(),
                spot_id_value=5,
            ),
        )
        q = MemoryRetrievalQueryDto(
            entity_ids=(),
            location_ids=(),
            world_object_ids=(),
            spot_ids=(5,),
        )
        got = retriever.retrieve_for_prediction(
            player_id, "現在地: 広場", [], query_dto=q
        )
        assert "広場でクエストを受けた" in got

    def test_retrieve_with_scope_keys_returns_relation_memory(
        self, retriever, episode_store, player_id
    ):
        """scope_keys で quest/guild/shop の relation memory が引ける"""
        episode_store.add(
            player_id,
            _make_episode(
                "e_quest",
                context_summary="伝説の剣クエストを受諾した",
                scope_keys=("quest:1",),
            ),
        )
        episode_store.add(
            player_id,
            _make_episode(
                "e_guild",
                context_summary="ギルドに寄付した",
                scope_keys=("guild:3",),
            ),
        )
        q = MemoryRetrievalQueryDto(
            entity_ids=(),
            location_ids=(),
            world_object_ids=(),
            spot_ids=(),
            scope_keys=("quest:1",),
        )
        got = retriever.retrieve_for_prediction(
            player_id, "現在地: 広場", [], query_dto=q
        )
        assert "伝説の剣" in got or "クエスト" in got

    def test_build_query_includes_guild_and_shop_scope_keys(self):
        """build_memory_retrieval_query_from_state は guild_ids と nearby_shop_ids を scope_keys に含める"""
        mock_dto = type("MockDto", (), {})()
        mock_dto.current_spot_id = 5
        mock_dto.current_spot_name = "広場"
        mock_dto.area_name = None
        mock_dto.connected_spot_ids = set()
        mock_dto.connected_spot_names = set()
        mock_dto.visible_objects = []
        mock_dto.notable_objects = []
        mock_dto.actionable_objects = []
        mock_dto.available_moves = []
        mock_dto.active_conversation = None
        mock_dto.active_quest_ids = []
        mock_dto.guild_ids = [3, 5]
        mock_dto.nearby_shop_ids = [9]
        q = build_memory_retrieval_query_from_state(
            mock_dto, ["talk_to"], current_state_summary=None
        )
        assert "guild:3" in q.scope_keys
        assert "guild:5" in q.scope_keys
        assert "shop:9" in q.scope_keys
