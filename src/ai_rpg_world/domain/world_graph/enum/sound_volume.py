from enum import Enum


class SoundVolumeEnum(str, Enum):
    """発話の音量（スポットグラフ上の音の届くホップ数）"""

    WHISPER = "WHISPER"  # 同一スポットのみ
    NORMAL = "NORMAL"  # 同一 + 隣接
    SHOUT = "SHOUT"  # 同一 + 隣接 + 2 ホップ先

    def max_hops(self) -> int:
        if self == SoundVolumeEnum.WHISPER:
            return 0
        if self == SoundVolumeEnum.NORMAL:
            return 1
        return 2
