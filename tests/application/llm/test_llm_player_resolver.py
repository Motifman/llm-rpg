"""SetBasedLlmPlayerResolver / ProfileBasedLlmPlayerResolver のテスト（正常・境界・例外）"""

import pytest
from unittest.mock import MagicMock

from ai_rpg_world.application.llm.services.llm_player_resolver import (
    ProfileBasedLlmPlayerResolver,
    SetBasedLlmPlayerResolver,
)
from ai_rpg_world.domain.player.aggregate.player_profile_aggregate import (
    PlayerProfileAggregate,
)
from ai_rpg_world.domain.player.enum.player_enum import ControlType
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.value_object.player_name import PlayerName


class TestSetBasedLlmPlayerResolverIsLlmControlled:
    """is_llm_controlled の正常・境界ケース"""

    def test_returns_true_when_player_id_in_set(self):
        """登録済みプレイヤーIDなら True"""
        resolver = SetBasedLlmPlayerResolver({1, 3, 5})
        assert resolver.is_llm_controlled(PlayerId(1)) is True
        assert resolver.is_llm_controlled(PlayerId(3)) is True
        assert resolver.is_llm_controlled(PlayerId(5)) is True

    def test_returns_false_when_player_id_not_in_set(self):
        """未登録プレイヤーIDなら False"""
        resolver = SetBasedLlmPlayerResolver({1, 2})
        assert resolver.is_llm_controlled(PlayerId(3)) is False
        assert resolver.is_llm_controlled(PlayerId(99)) is False

    def test_empty_set_all_false(self):
        """空集合なら常に False"""
        resolver = SetBasedLlmPlayerResolver(set())
        assert resolver.is_llm_controlled(PlayerId(1)) is False

    def test_accepts_frozenset(self):
        """frozenset も受け付ける"""
        resolver = SetBasedLlmPlayerResolver(frozenset([1]))
        assert resolver.is_llm_controlled(PlayerId(1)) is True
        assert resolver.is_llm_controlled(PlayerId(2)) is False

    def test_player_id_not_player_id_raises_type_error(self):
        """player_id が PlayerId でないとき TypeError"""
        resolver = SetBasedLlmPlayerResolver({1})
        with pytest.raises(TypeError, match="player_id must be PlayerId"):
            resolver.is_llm_controlled(1)  # type: ignore[arg-type]
        with pytest.raises(TypeError, match="player_id must be PlayerId"):
            resolver.is_llm_controlled(None)  # type: ignore[arg-type]


class TestSetBasedLlmPlayerResolverInit:
    """コンストラクタのバリデーション"""

    def test_llm_player_ids_not_set_raises_type_error(self):
        """llm_player_ids が set/frozenset でないとき TypeError"""
        with pytest.raises(TypeError, match="llm_player_ids must be a set or frozenset"):
            SetBasedLlmPlayerResolver([1, 2])  # type: ignore[arg-type]
        with pytest.raises(TypeError, match="llm_player_ids must be a set or frozenset"):
            SetBasedLlmPlayerResolver((1, 2))  # type: ignore[arg-type]
        with pytest.raises(TypeError, match="llm_player_ids must be a set or frozenset"):
            SetBasedLlmPlayerResolver(None)  # type: ignore[arg-type]

    def test_llm_player_ids_contains_non_positive_raises_value_error(self):
        """0 または負の整数が含まれるとき ValueError"""
        with pytest.raises(ValueError, match="positive integers only"):
            SetBasedLlmPlayerResolver({1, 0})
        with pytest.raises(ValueError, match="positive integers only"):
            SetBasedLlmPlayerResolver({1, -1})

    def test_llm_player_ids_contains_non_int_raises_value_error(self):
        """整数でない値が含まれるとき ValueError（isinstance(pid, int) で弾かれる）"""
        with pytest.raises(ValueError, match="positive integers only"):
            SetBasedLlmPlayerResolver({1, "2"})  # type: ignore[arg-type]


class TestProfileBasedLlmPlayerResolverIsLlmControlled:
    """ProfileBasedLlmPlayerResolver.is_llm_controlled の正常・境界ケース"""

    def test_returns_true_when_profile_control_type_llm(self):
        """プロフィールの control_type が LLM なら True"""
        profile = PlayerProfileAggregate.create(
            PlayerId(1),
            PlayerName("LLMPlayer"),
            control_type=ControlType.LLM,
        )
        repo = MagicMock()
        repo.find_by_id.return_value = profile
        resolver = ProfileBasedLlmPlayerResolver(repo)
        assert resolver.is_llm_controlled(PlayerId(1)) is True

    def test_returns_false_when_profile_control_type_human(self):
        """プロフィールの control_type が HUMAN なら False"""
        profile = PlayerProfileAggregate.create(
            PlayerId(1),
            PlayerName("HumanPlayer"),
            control_type=ControlType.HUMAN,
        )
        repo = MagicMock()
        repo.find_by_id.return_value = profile
        resolver = ProfileBasedLlmPlayerResolver(repo)
        assert resolver.is_llm_controlled(PlayerId(1)) is False

    def test_returns_false_when_profile_not_found(self):
        """プロフィールが存在しない場合は False"""
        repo = MagicMock()
        repo.find_by_id.return_value = None
        resolver = ProfileBasedLlmPlayerResolver(repo)
        assert resolver.is_llm_controlled(PlayerId(999)) is False

    def test_returns_false_when_profile_control_type_bot(self):
        """プロフィールの control_type が BOT なら False"""
        profile = PlayerProfileAggregate.create(
            PlayerId(1),
            PlayerName("BotPlayer"),
            control_type=ControlType.BOT,
        )
        repo = MagicMock()
        repo.find_by_id.return_value = profile
        resolver = ProfileBasedLlmPlayerResolver(repo)
        assert resolver.is_llm_controlled(PlayerId(1)) is False

    def test_calls_find_by_id_with_given_player_id(self):
        """find_by_id に渡した player_id でリポジトリが呼ばれる"""
        repo = MagicMock()
        repo.find_by_id.return_value = None
        resolver = ProfileBasedLlmPlayerResolver(repo)
        resolver.is_llm_controlled(PlayerId(42))
        repo.find_by_id.assert_called_once_with(PlayerId(42))

    def test_player_id_not_player_id_raises_type_error(self):
        """player_id が PlayerId でないとき TypeError"""
        repo = MagicMock()
        resolver = ProfileBasedLlmPlayerResolver(repo)
        with pytest.raises(TypeError, match="player_id must be PlayerId"):
            resolver.is_llm_controlled(1)  # type: ignore[arg-type]
        with pytest.raises(TypeError, match="player_id must be PlayerId"):
            resolver.is_llm_controlled(None)  # type: ignore[arg-type]


class TestProfileBasedLlmPlayerResolverInit:
    """ProfileBasedLlmPlayerResolver コンストラクタのバリデーション"""

    def test_repository_none_raises_type_error(self):
        """player_profile_repository が None のとき TypeError"""
        with pytest.raises(TypeError, match="player_profile_repository must not be None"):
            ProfileBasedLlmPlayerResolver(None)  # type: ignore[arg-type]
