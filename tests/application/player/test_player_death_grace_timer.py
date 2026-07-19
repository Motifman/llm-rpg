"""PlayerDeathGraceTimer の挙動検証 (Issue #621)。

ダウンしてから DEAD 確定までの 30 tick 猶予を管理する service。
旧仕様 (= PlayerDownedOutcomeHandler が即時 DEAD 確定) から
「30 tick 経過後に確定」に変えるための pending state を保持する。

責務:
- ダウン時に player_id と downed_at_tick を登録 (`register`)
- revive 時に削除 (`cancel`)
- tick 毎に「猶予を過ぎた player_id」を返す (`overdue_players`)
- 確認用に「pending か?」を返す (`is_pending`)
"""

from __future__ import annotations

import pytest

from ai_rpg_world.application.player.services.player_death_grace_timer import (
    PlayerDeathGraceTimer,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class TestRegisterAndCancel:
    """pending state の出入りを管理する基本動作。"""

    def test_register_pending_true(self) -> None:
        """register すると is pending が True になる。"""
        timer = PlayerDeathGraceTimer()
        timer.register(PlayerId(1), downed_at_tick=10)
        assert timer.is_pending(PlayerId(1)) is True

    def test_register_player_pending_false(self) -> None:
        """register していない player は is pending False。"""
        timer = PlayerDeathGraceTimer()
        assert timer.is_pending(PlayerId(99)) is False

    def test_returns_cancel_pending_false(self) -> None:
        """revive で grace 期間がキャンセルされた状態を表現する。"""
        timer = PlayerDeathGraceTimer()
        timer.register(PlayerId(1), downed_at_tick=10)
        timer.cancel(PlayerId(1))
        assert timer.is_pending(PlayerId(1)) is False

    def test_pending_player_cancel_raises_exception(self) -> None:
        """revive event が重複発火しても破綻しない冪等性。"""
        timer = PlayerDeathGraceTimer()
        timer.cancel(PlayerId(99))  # no-op
        # 例外なく完了

    def test_same_player_two_register_tick_overwritten(self) -> None:
        """ダウン後に revive、再ダウン (= 短時間で 2 度倒れた) ケース。
        2 度目の register が新しい起点となる (= 30 tick 猶予がリセット)。
        """
        timer = PlayerDeathGraceTimer()
        timer.register(PlayerId(1), downed_at_tick=10)
        timer.register(PlayerId(1), downed_at_tick=50)
        # downed_at_tick が更新されているので、tick 60 (= 10+50 経過) ではまだ overdue ではない
        overdue = timer.overdue_players(current_tick=60, grace_ticks=30)
        assert PlayerId(1) not in overdue
        # tick 80 (= 50+30 経過) では overdue
        overdue = timer.overdue_players(current_tick=80, grace_ticks=30)
        assert PlayerId(1) in overdue


class TestOverduePlayers:
    """猶予 tick を過ぎた player を抽出する挙動。"""

    def test_grace_tick_before_overdue_not_included(self) -> None:
        """gracetick 経過前は overdue に含まれない。"""
        timer = PlayerDeathGraceTimer()
        timer.register(PlayerId(1), downed_at_tick=10)
        # tick 39 = 29 tick 経過 (= grace 30 未満)
        overdue = timer.overdue_players(current_tick=39, grace_ticks=30)
        assert PlayerId(1) not in overdue

    def test_grace_tick_overdue_included(self) -> None:
        """downed_at_tick + grace_ticks = current_tick で確定 (= 境界が inclusive)。"""
        timer = PlayerDeathGraceTimer()
        timer.register(PlayerId(1), downed_at_tick=10)
        overdue = timer.overdue_players(current_tick=40, grace_ticks=30)
        assert PlayerId(1) in overdue

    def test_grace_tick_after_overdue_included(self) -> None:
        """gracetick 経過後は overdue に含まれる。"""
        timer = PlayerDeathGraceTimer()
        timer.register(PlayerId(1), downed_at_tick=10)
        overdue = timer.overdue_players(current_tick=100, grace_ticks=30)
        assert PlayerId(1) in overdue

    def test_multiple_player_overdue_independently(self) -> None:
        """複数 player の overdue を独立に判定。"""
        timer = PlayerDeathGraceTimer()
        timer.register(PlayerId(1), downed_at_tick=10)   # tick 40 で overdue
        timer.register(PlayerId(2), downed_at_tick=20)   # tick 50 で overdue
        timer.register(PlayerId(3), downed_at_tick=30)   # tick 60 で overdue
        overdue = timer.overdue_players(current_tick=45, grace_ticks=30)
        assert PlayerId(1) in overdue
        assert PlayerId(2) not in overdue
        assert PlayerId(3) not in overdue

    def test_cancel_player_overdue_not_included(self) -> None:
        """revive 後の player は猶予判定の対象外。"""
        timer = PlayerDeathGraceTimer()
        timer.register(PlayerId(1), downed_at_tick=10)
        timer.cancel(PlayerId(1))
        overdue = timer.overdue_players(current_tick=100, grace_ticks=30)
        assert PlayerId(1) not in overdue

    def test_empty_pending_players_returns_empty_overdue_players(self) -> None:
        """pendingplayer が空なら overdue も空。"""
        timer = PlayerDeathGraceTimer()
        overdue = timer.overdue_players(current_tick=100, grace_ticks=30)
        assert overdue == []


class TestValidation:
    """不正な入力を弾く。"""

    def test_register_downed_tick_non(self) -> None:
        """register の downedattick は非負。"""
        timer = PlayerDeathGraceTimer()
        with pytest.raises(ValueError):
            timer.register(PlayerId(1), downed_at_tick=-1)

    def test_overdue_players_grace_ticks_non(self) -> None:
        """overdueplayers の graceticks は非負。"""
        timer = PlayerDeathGraceTimer()
        with pytest.raises(ValueError):
            timer.overdue_players(current_tick=10, grace_ticks=-1)

    def test_register_player_id_player_id(self) -> None:
        """register の player id は PlayerId。"""
        timer = PlayerDeathGraceTimer()
        with pytest.raises(TypeError):
            timer.register(1, downed_at_tick=0)  # type: ignore[arg-type]


class TestGetDownedAtTick:
    """Issue #621 Phase 5: post hoc 観測 (= 「N tick 意識を失っていた」) を組み立てる
    のに ``downed_at_tick`` を読み出すための getter。cancel される前に handler
    から参照する用途。"""

    def test_returns_register_player_tick(self) -> None:
        """register された player の tick を返す。"""
        timer = PlayerDeathGraceTimer()
        pid = PlayerId(1)
        timer.register(pid, downed_at_tick=7)
        assert timer.get_downed_at_tick(pid) == 7

    def test_returns_none_register_player(self) -> None:
        """register していない player は None を返す。"""
        timer = PlayerDeathGraceTimer()
        assert timer.get_downed_at_tick(PlayerId(99)) is None

    def test_returns_none_cancel_after(self) -> None:
        """cancel 後は None を返す。"""
        timer = PlayerDeathGraceTimer()
        pid = PlayerId(1)
        timer.register(pid, downed_at_tick=7)
        timer.cancel(pid)
        assert timer.get_downed_at_tick(pid) is None

    def test_player_id_player_id(self) -> None:
        """player id は PlayerId。"""
        timer = PlayerDeathGraceTimer()
        with pytest.raises(TypeError):
            timer.get_downed_at_tick(1)  # type: ignore[arg-type]
