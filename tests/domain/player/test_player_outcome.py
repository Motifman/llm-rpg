"""PlayerOutcomeEnum + PlayerOutcomeRegistry の挙動検証 (Phase E-3)。"""

from __future__ import annotations

import pytest

from ai_rpg_world.domain.player.enum.player_outcome_enum import PlayerOutcomeEnum
from ai_rpg_world.domain.player.service.player_outcome_registry import (
    PlayerOutcomeRegistry,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class TestPlayerOutcomeEnum:
    """Enum の基本性質。"""

    def test_UNRESOLVED_は_未確定として扱う(self) -> None:
        assert PlayerOutcomeEnum.UNRESOLVED.is_resolved is False

    def test_RESCUED_DEAD_STRANDED_は_確定として扱う(self) -> None:
        assert PlayerOutcomeEnum.RESCUED.is_resolved is True
        assert PlayerOutcomeEnum.DEAD.is_resolved is True
        assert PlayerOutcomeEnum.STRANDED.is_resolved is True

    def test_display_label_は日本語(self) -> None:
        assert PlayerOutcomeEnum.RESCUED.display_label == "救助"
        assert PlayerOutcomeEnum.DEAD.display_label == "死亡"
        assert PlayerOutcomeEnum.STRANDED.display_label == "取り残され"


class TestRegistryInit:
    """initial 状態と問い合わせ。"""

    def test_new_for_players_で_全員_UNRESOLVED(self) -> None:
        reg = PlayerOutcomeRegistry.new_for_players([PlayerId(1), PlayerId(2)])
        assert reg.get_outcome(PlayerId(1)) is PlayerOutcomeEnum.UNRESOLVED
        assert reg.get_outcome(PlayerId(2)) is PlayerOutcomeEnum.UNRESOLVED

    def test_未登録プレイヤーの_get_outcome_は_UNRESOLVED(self) -> None:
        """登録されていない id を引いても auto-init で UNRESOLVED が返る。"""
        reg = PlayerOutcomeRegistry()
        assert reg.get_outcome(PlayerId(99)) is PlayerOutcomeEnum.UNRESOLVED

    def test_空_registry_の_all_resolved_は_True(self) -> None:
        """vacuous truth: 「全員」が空なら全員確定扱い。"""
        reg = PlayerOutcomeRegistry()
        assert reg.all_resolved() is True


class TestSetOutcome:
    """outcome の確定遷移。"""

    def test_UNRESOLVED_から_DEAD_への遷移は変更扱い(self) -> None:
        reg = PlayerOutcomeRegistry.new_for_players([PlayerId(1)])
        changed = reg.set_outcome(PlayerId(1), PlayerOutcomeEnum.DEAD)
        assert changed is True
        assert reg.get_outcome(PlayerId(1)) is PlayerOutcomeEnum.DEAD

    def test_既に_resolved_なら_上書きされず_no_op(self) -> None:
        """RESCUED で確定したプレイヤーが後から DEAD event を受けても上書きしない。"""
        reg = PlayerOutcomeRegistry.new_for_players([PlayerId(1)])
        reg.set_outcome(PlayerId(1), PlayerOutcomeEnum.RESCUED)
        changed = reg.set_outcome(PlayerId(1), PlayerOutcomeEnum.DEAD)
        assert changed is False
        assert reg.get_outcome(PlayerId(1)) is PlayerOutcomeEnum.RESCUED

    def test_UNRESOLVED_への遷移は_no_op(self) -> None:
        """UNRESOLVED 設定は意味がないので silent に skip。"""
        reg = PlayerOutcomeRegistry.new_for_players([PlayerId(1)])
        changed = reg.set_outcome(PlayerId(1), PlayerOutcomeEnum.UNRESOLVED)
        assert changed is False


class TestCallback:
    """outcome 変化 callback の呼び出し挙動。"""

    def test_変化時に_callback_が呼ばれる(self) -> None:
        reg = PlayerOutcomeRegistry.new_for_players([PlayerId(1)])
        calls: list[tuple] = []
        reg.register_callback(
            lambda pid, old, new: calls.append((int(pid), old.value, new.value))
        )

        reg.set_outcome(PlayerId(1), PlayerOutcomeEnum.DEAD)

        assert calls == [(1, "UNRESOLVED", "DEAD")]

    def test_既_resolved_への_set_は_callback_を呼ばない(self) -> None:
        reg = PlayerOutcomeRegistry.new_for_players([PlayerId(1)])
        reg.set_outcome(PlayerId(1), PlayerOutcomeEnum.RESCUED)
        calls: list[tuple] = []
        reg.register_callback(lambda pid, old, new: calls.append((pid, old, new)))

        # 既に RESCUED なので DEAD への遷移は無視され、callback も呼ばれない
        reg.set_outcome(PlayerId(1), PlayerOutcomeEnum.DEAD)

        assert calls == []


class TestAggregateQueries:
    """all_resolved / unresolved_player_ids の整合性。"""

    def test_全員確定したら_all_resolved_は_True(self) -> None:
        reg = PlayerOutcomeRegistry.new_for_players([PlayerId(1), PlayerId(2)])
        reg.set_outcome(PlayerId(1), PlayerOutcomeEnum.RESCUED)
        reg.set_outcome(PlayerId(2), PlayerOutcomeEnum.DEAD)
        assert reg.all_resolved() is True

    def test_1_人_未確定なら_unresolved_に出る(self) -> None:
        reg = PlayerOutcomeRegistry.new_for_players(
            [PlayerId(1), PlayerId(2), PlayerId(3)]
        )
        reg.set_outcome(PlayerId(1), PlayerOutcomeEnum.DEAD)
        unresolved = reg.unresolved_player_ids()
        unresolved_ids = {int(p) for p in unresolved}
        assert unresolved_ids == {2, 3}
