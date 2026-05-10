from enum import Enum


class TemperatureEnum(Enum):
    FREEZING = "FREEZING"
    COLD = "COLD"
    NORMAL = "NORMAL"
    WARM = "WARM"
    HOT = "HOT"

    @property
    def severity(self) -> int:
        """温度の順序を 0 (寒) ～ 4 (暑) の整数で返す。比較に使う。

        Phase 4-O B: モンスターの comfort range 判定で使う。`min/max
        comfortable` の境界が連続軸でないと「寒すぎ / 暑すぎ」が表現
        できないため、enum 値とは別に severity を持つ。
        """
        return _SEVERITY[self]


_SEVERITY: dict[TemperatureEnum, int] = {
    TemperatureEnum.FREEZING: 0,
    TemperatureEnum.COLD: 1,
    TemperatureEnum.NORMAL: 2,
    TemperatureEnum.WARM: 3,
    TemperatureEnum.HOT: 4,
}
