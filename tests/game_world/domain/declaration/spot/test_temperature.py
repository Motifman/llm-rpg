from __future__ import annotations

from ai_rpg_world.game_world.domain.declaration.spot import Temperature


class TestTemperatureOrder:
    """Temperature が寒い順に比べられることを保証する。"""

    def test_temperatures_sort_from_coldest_to_hottest(self) -> None:
        """並べ替えると FREEZING、COLD、NORMAL、WARM、HOT の順になる。"""
        shuffled = [Temperature.HOT, Temperature.FREEZING, Temperature.WARM, Temperature.NORMAL, Temperature.COLD]

        ordered = sorted(shuffled)

        assert ordered == [
            Temperature.FREEZING,
            Temperature.COLD,
            Temperature.NORMAL,
            Temperature.WARM,
            Temperature.HOT,
        ]

    def test_colder_temperature_is_less_than_warmer_one(self) -> None:
        """寒い方が小さく、暑い方が大きい。同じ温度どうしは小さくも大きくもない。"""
        assert Temperature.COLD < Temperature.WARM
        assert Temperature.HOT > Temperature.NORMAL
        assert Temperature.NORMAL <= Temperature.NORMAL
        assert not Temperature.NORMAL < Temperature.NORMAL
