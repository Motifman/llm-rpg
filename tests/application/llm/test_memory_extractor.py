"""RuleBasedMemoryExtractor のテスト（正常・境界・例外）"""

import pytest
from datetime import datetime

from ai_rpg_world.application.llm.contracts.dtos import EpisodeMemoryEntry
from ai_rpg_world.application.llm.services.memory_extractor import (
    RuleBasedMemoryExtractor,
)
from ai_rpg_world.application.observation.contracts.dtos import (
    ObservationEntry,
    ObservationOutput,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


def _obs(
    prose: str,
    *,
    structured: dict | None = None,
    causes_interrupt: bool = False,
) -> ObservationEntry:
    return ObservationEntry(
        occurred_at=datetime.now(),
        output=ObservationOutput(
            prose=prose,
            structured=structured or {},
            observation_category="self_only",
            causes_interrupt=causes_interrupt,
        ),
    )


class TestRuleBasedMemoryExtractor:
    """RuleBasedMemoryExtractor の正常・境界・例外ケース"""

    @pytest.fixture
    def extractor(self):
        return RuleBasedMemoryExtractor()

    @pytest.fixture
    def player_id(self):
        return PlayerId(1)

    def test_extract_returns_one_episode_with_action_and_result(
        self, extractor, player_id
    ):
        """extract は行動要約と結果要約から 1 件のエピソードを返す"""
        episodes = extractor.extract(
            player_id,
            overflow_observations=[],
            action_summary="move_to_destination を実行しました。",
            result_summary="目的地に到着しました。",
        )
        assert len(episodes) == 1
        assert isinstance(episodes[0], EpisodeMemoryEntry)
        assert episodes[0].action_taken == "move_to_destination を実行しました。"
        assert episodes[0].outcome_summary == "目的地に到着しました。"
        assert episodes[0].context_summary == "（特になし）"
        assert episodes[0].importance == "medium"
        assert episodes[0].recall_count == 0

    def test_extract_uses_overflow_prose_as_context_summary(
        self, extractor, player_id
    ):
        """溢れた観測のプローズが context_summary に使われる"""
        episodes = extractor.extract(
            player_id,
            overflow_observations=[_obs("洞窟に入った"), _obs("モンスターを発見")],
            action_summary="攻撃した",
            result_summary="倒した",
        )
        assert len(episodes) == 1
        assert "洞窟" in episodes[0].context_summary
        assert "モンスター" in episodes[0].context_summary

    def test_extract_populates_entity_ids_and_location_from_structured(
        self, extractor, player_id
    ):
        """structured の名前情報と場所情報が記憶メタデータに反映される"""
        episodes = extractor.extract(
            player_id,
            overflow_observations=[
                _obs(
                    "老人に話しかけた",
                    structured={"npc_name": "老人", "spot_name": "洞窟入口"},
                    causes_interrupt=True,
                )
            ],
            action_summary="会話した",
            result_summary="依頼を受けた",
        )

        assert episodes[0].entity_ids == ("老人", "洞窟入口")
        assert episodes[0].location_id == "洞窟入口"
        assert episodes[0].importance == "high"
        assert episodes[0].surprise is True

    def test_extract_does_not_save_when_no_conditions_met(self, extractor, player_id):
        """保存条件を一切満たさないときはエピソードを保存しない（ノイズ抑制）"""
        episodes = extractor.extract(
            player_id,
            overflow_observations=[],
            action_summary="待機",
            result_summary="何も起きなかった",
        )
        assert len(episodes) == 0

    def test_extract_saves_when_has_clear_context(self, extractor, player_id):
        """明確な観測文脈（5文字以上）があれば保存する"""
        episodes = extractor.extract(
            player_id,
            overflow_observations=[_obs("洞窟の入口で待機した")],
            action_summary="待機",
            result_summary="何も起きなかった",
        )
        assert len(episodes) == 1
        assert "洞窟" in episodes[0].context_summary

    def test_extract_saves_when_has_strong_result(self, extractor, player_id):
        """強い成功/失敗結果があれば overflow が空でも保存する"""
        episodes = extractor.extract(
            player_id,
            overflow_observations=[],
            action_summary="open_chest を実行",
            result_summary="回復ポーションを入手しました",
        )
        assert len(episodes) == 1
        assert "入手" in episodes[0].outcome_summary

    def test_extract_player_id_none_raises_type_error(self, extractor):
        """player_id が None のとき TypeError"""
        with pytest.raises(TypeError, match="player_id must be PlayerId"):
            extractor.extract(
                None,  # type: ignore[arg-type]
                [],
                "action",
                "result",
            )

    def test_extract_overflow_not_list_raises_type_error(self, extractor, player_id):
        """overflow_observations が list でないとき TypeError"""
        with pytest.raises(TypeError, match="overflow_observations must be list"):
            extractor.extract(
                player_id,
                "not a list",  # type: ignore[arg-type]
                "action",
                "result",
            )

    def test_extract_overflow_contains_non_observation_raises_type_error(
        self, extractor, player_id
    ):
        """overflow_observations の要素が ObservationEntry でないとき TypeError"""
        with pytest.raises(
            TypeError,
            match="overflow_observations must contain only ObservationEntry",
        ):
            extractor.extract(
                player_id,
                [_obs("a"), "invalid"],  # type: ignore[list-item]
                "action",
                "result",
            )

    def test_extract_action_summary_not_str_raises_type_error(
        self, extractor, player_id
    ):
        """action_summary が str でないとき TypeError"""
        with pytest.raises(TypeError, match="action_summary must be str"):
            extractor.extract(player_id, [], 123, "result")  # type: ignore[arg-type]

    def test_extract_result_summary_not_str_raises_type_error(
        self, extractor, player_id
    ):
        """result_summary が str でないとき TypeError"""
        with pytest.raises(TypeError, match="result_summary must be str"):
            extractor.extract(player_id, [], "action", 456)  # type: ignore[arg-type]
