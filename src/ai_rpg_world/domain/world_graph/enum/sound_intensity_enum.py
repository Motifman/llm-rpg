"""spot の環境音の強さ (Phase 5: 五感観察システム)。

`SpotAtmosphere.sound_intensity` で持つ列挙型。隣接 spot への音の伝搬
を計算する際に「1 hop で 1 段階減衰」する単純なモデルで使う
(intensity の `level` 整数を 1 ずつ下げる)。

将来の拡張 (動的音源 / 接続種別による減衰調整) でも、この強度軸を
共通の単位として使う。
"""

from __future__ import annotations

from enum import Enum


class SoundIntensityEnum(Enum):
    """spot の音の強さ。`level` で順序付け可能。"""

    SILENT = "SILENT"        # 完全な静寂
    FAINT = "FAINT"          # かすかな音 (虫の声、風など)
    MODERATE = "MODERATE"    # 通常の環境音 (川のせせらぎ、人の話し声)
    LOUD = "LOUD"            # はっきりした音 (戦闘音、咆哮、機械音)

    @property
    def level(self) -> int:
        """音の強さを 0 (無音) - 3 (大音響) の整数で返す。

        Phase 5: 隣接 spot への伝搬で「1 hop = 1 段階減衰」を表現する
        ために整数化。`SILENT.level == 0` を「減衰しきって聞こえない」
        境界として扱う。
        """
        return _LEVEL[self]

    def attenuate(self, hops: int = 1) -> "SoundIntensityEnum":
        """指定 hop 数だけ減衰させた強度を返す。

        - SILENT は何 hop 減衰しても SILENT
        - LOUD を 1 hop → MODERATE、2 hop → FAINT、3 hop → SILENT
        - hops <= 0 は self を返す (減衰なし)
        """
        if hops <= 0:
            return self
        new_level = max(0, self.level - hops)
        return _BY_LEVEL[new_level]


_LEVEL: dict[SoundIntensityEnum, int] = {
    SoundIntensityEnum.SILENT: 0,
    SoundIntensityEnum.FAINT: 1,
    SoundIntensityEnum.MODERATE: 2,
    SoundIntensityEnum.LOUD: 3,
}

_BY_LEVEL: dict[int, SoundIntensityEnum] = {
    v: k for k, v in _LEVEL.items()
}
