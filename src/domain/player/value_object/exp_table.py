from dataclasses import dataclass
import math
from src.domain.player.exception import ExpTableValidationException


@dataclass(frozen=True)
class ExpTable:
    """経験値テーブルを表すバリューオブジェクト

    レベルnに到達するための累積経験値を計算する。
    累積経験値曲線をパラメトリックに調整可能。
    """
    base_exp: float  # 基本経験値量
    exponent: float  # 指数（成長曲線の傾き）
    level_offset: float = 0.0  # レベルオフセット

    def __post_init__(self):
        if self.base_exp <= 0:
            raise ExpTableValidationException(f"base_exp must be greater than 0. base_exp: {self.base_exp}")
        if self.exponent <= 0:
            raise ExpTableValidationException(f"exponent must be greater than 0. exponent: {self.exponent}")

    def get_required_exp_for_level(self, level: int) -> int:
        """指定レベルに到達するための累積経験値を返す

        Args:
            level: 目標レベル

        Returns:
            累積経験値
        """
        if level <= 1:
            return 0

        # 累積経験値 = base_exp * ((level - 1 + level_offset) ^ exponent)
        exp = self.base_exp * math.pow(level - 1 + self.level_offset, self.exponent)
        return int(exp)

    def get_level_from_exp(self, total_exp: int) -> int:
        """累積経験値からレベルを計算する

        Args:
            total_exp: 累積経験値

        Returns:
            現在のレベル
        """
        if total_exp <= 0:
            return 1

        # レベルを順番にチェックして、必要な経験値を超えるレベルを見つける
        level = 1
        while True:
            required_exp_for_next = self.get_required_exp_for_level(level + 1)
            if total_exp < required_exp_for_next:
                return level
            level += 1
