from __future__ import annotations

import pytest

from ai_rpg_world.game_world.domain.exception.game_world_exception import ValueOutOfRangeException
from ai_rpg_world.game_world.domain.sound import SoundLevel, SoundLoss


class TestSoundLoss:
    """SoundLoss が 0 以上の減衰を表し、減衰どうしを足せることを保証する。"""

    def test_zero_is_accepted_for_an_open_passage(self) -> None:
        """書かなければ「通れる、減衰 0」になる通路の状態のため、0 を受け付ける。"""
        assert SoundLoss(0).value == 0

    def test_negative_raises_domain_exception(self) -> None:
        """負の値を渡すと ValueOutOfRangeException を投げる。"""
        with pytest.raises(ValueOutOfRangeException):
            SoundLoss(-1)

    @pytest.mark.parametrize("raw", [1.5, True])
    def test_non_integer_raises_domain_exception(self, raw: object) -> None:
        """整数でない値 (小数、真偽値) を渡すと ValueOutOfRangeException を投げる。"""
        with pytest.raises(ValueOutOfRangeException):
            SoundLoss(raw)  # type: ignore[arg-type]

    def test_plus_sums_losses(self) -> None:
        """通路ごとの減衰 15 と通路の状態の減衰 10 を足すと 25 になる (SoundLink.loss)。"""
        assert SoundLoss(15).plus(SoundLoss(10)) == SoundLoss(25)


class TestSoundLevel:
    """SoundLevel が音の大きさを表し、減衰で弱まり、ほかの大きさと比べられることを保証する。"""

    def test_weakened_by_subtracts_the_loss(self) -> None:
        """大きさ 60 が減衰 15 で弱まると 45 になる。"""
        assert SoundLevel(60).weakened_by(SoundLoss(15)) == SoundLevel(45)

    def test_is_below_is_true_only_when_strictly_smaller(self) -> None:
        """is_below は小さいときだけ真で、等しいときは偽になる (下限ちょうどの音は聞こえる)。"""
        assert SoundLevel(19).is_below(SoundLevel(20))
        assert not SoundLevel(20).is_below(SoundLevel(20))
        assert not SoundLevel(21).is_below(SoundLevel(20))

    def test_weakened_by_stops_at_zero(self) -> None:
        """大きさより大きい減衰で弱めると、負にならず 0 で止まる。"""
        assert SoundLevel(10).weakened_by(SoundLoss(15)) == SoundLevel(0)

    def test_zero_is_accepted_for_silence(self) -> None:
        """弱まりきった音を表す 0 を受け付ける。"""
        assert SoundLevel(0).value == 0

    def test_negative_raises_domain_exception(self) -> None:
        """負の値を渡すと ValueOutOfRangeException を投げる。"""
        with pytest.raises(ValueOutOfRangeException):
            SoundLevel(-1)

    @pytest.mark.parametrize("raw", [1.5, True])
    def test_non_integer_raises_domain_exception(self, raw: object) -> None:
        """整数でない値 (小数、真偽値) を渡すと ValueOutOfRangeException を投げる。"""
        with pytest.raises(ValueOutOfRangeException):
            SoundLevel(raw)  # type: ignore[arg-type]
