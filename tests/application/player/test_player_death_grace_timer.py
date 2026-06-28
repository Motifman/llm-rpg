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

    def test_register_すると_is_pending_が_True_になる(self) -> None:
        timer = PlayerDeathGraceTimer()
        timer.register(PlayerId(1), downed_at_tick=10)
        assert timer.is_pending(PlayerId(1)) is True

    def test_register_していない_player_は_is_pending_False(self) -> None:
        timer = PlayerDeathGraceTimer()
        assert timer.is_pending(PlayerId(99)) is False

    def test_cancel_すると_is_pending_が_False_に_戻る(self) -> None:
        """revive で grace 期間がキャンセルされた状態を表現する。"""
        timer = PlayerDeathGraceTimer()
        timer.register(PlayerId(1), downed_at_tick=10)
        timer.cancel(PlayerId(1))
        assert timer.is_pending(PlayerId(1)) is False

    def test_pending_でない_player_を_cancel_しても_例外にならない(self) -> None:
        """revive event が重複発火しても破綻しない冪等性。"""
        timer = PlayerDeathGraceTimer()
        timer.cancel(PlayerId(99))  # no-op
        # 例外なく完了

    def test_同じ_player_を_2_回_register_すると_最新の_tick_で_上書きされる(self) -> None:
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

    def test_grace_tick_経過前は_overdue_に_含まれない(self) -> None:
        timer = PlayerDeathGraceTimer()
        timer.register(PlayerId(1), downed_at_tick=10)
        # tick 39 = 29 tick 経過 (= grace 30 未満)
        overdue = timer.overdue_players(current_tick=39, grace_ticks=30)
        assert PlayerId(1) not in overdue

    def test_grace_tick_ちょうどで_overdue_に_含まれる(self) -> None:
        """downed_at_tick + grace_ticks = current_tick で確定 (= 境界が inclusive)。"""
        timer = PlayerDeathGraceTimer()
        timer.register(PlayerId(1), downed_at_tick=10)
        overdue = timer.overdue_players(current_tick=40, grace_ticks=30)
        assert PlayerId(1) in overdue

    def test_grace_tick_経過後は_overdue_に_含まれる(self) -> None:
        timer = PlayerDeathGraceTimer()
        timer.register(PlayerId(1), downed_at_tick=10)
        overdue = timer.overdue_players(current_tick=100, grace_ticks=30)
        assert PlayerId(1) in overdue

    def test_複数_player_の_overdue_を_独立に_判定(self) -> None:
        timer = PlayerDeathGraceTimer()
        timer.register(PlayerId(1), downed_at_tick=10)   # tick 40 で overdue
        timer.register(PlayerId(2), downed_at_tick=20)   # tick 50 で overdue
        timer.register(PlayerId(3), downed_at_tick=30)   # tick 60 で overdue
        overdue = timer.overdue_players(current_tick=45, grace_ticks=30)
        assert PlayerId(1) in overdue
        assert PlayerId(2) not in overdue
        assert PlayerId(3) not in overdue

    def test_cancel_された_player_は_overdue_に_含まれない(self) -> None:
        """revive 後の player は猶予判定の対象外。"""
        timer = PlayerDeathGraceTimer()
        timer.register(PlayerId(1), downed_at_tick=10)
        timer.cancel(PlayerId(1))
        overdue = timer.overdue_players(current_tick=100, grace_ticks=30)
        assert PlayerId(1) not in overdue

    def test_pending_player_が_空_なら_overdue_も_空(self) -> None:
        timer = PlayerDeathGraceTimer()
        overdue = timer.overdue_players(current_tick=100, grace_ticks=30)
        assert overdue == []


class TestValidation:
    """不正な入力を弾く。"""

    def test_register_の_downed_at_tick_は_非負(self) -> None:
        timer = PlayerDeathGraceTimer()
        with pytest.raises(ValueError):
            timer.register(PlayerId(1), downed_at_tick=-1)

    def test_overdue_players_の_grace_ticks_は_非負(self) -> None:
        timer = PlayerDeathGraceTimer()
        with pytest.raises(ValueError):
            timer.overdue_players(current_tick=10, grace_ticks=-1)

    def test_register_の_player_id_は_PlayerId(self) -> None:
        timer = PlayerDeathGraceTimer()
        with pytest.raises(TypeError):
            timer.register(1, downed_at_tick=0)  # type: ignore[arg-type]
