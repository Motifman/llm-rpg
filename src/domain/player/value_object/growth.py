from dataclasses import dataclass
from .exp_table import ExpTable
from src.domain.player.exception import GrowthValidationException


@dataclass(frozen=True)
class Growth:
    """レベルと経験値を管理するバリューオブジェクト"""
    level: int
    total_exp: int
    exp_table: ExpTable

    def __post_init__(self):
        if self.level <= 0:
            raise GrowthValidationException(f"level must be greater than 0. level: {self.level}")
        if self.total_exp < 0:
            raise GrowthValidationException(f"total_exp must be greater than or equal to 0. total_exp: {self.total_exp}")

        # 現在のレベルと経験値の整合性をチェック
        required_exp = self.exp_table.get_required_exp_for_level(self.level)
        if self.total_exp < required_exp:
            raise GrowthValidationException(f"total_exp {self.total_exp} is insufficient for level {self.level}. required: {required_exp}")

    def gain_exp(self, exp_amount: int) -> tuple['Growth', bool]:
        """経験値を獲得し、レベルアップ判定を行う

        Args:
            exp_amount: 獲得する経験値量

        Returns:
            tuple: (新しいGrowth, レベルアップしたか)
        """
        if exp_amount < 0:
            raise GrowthValidationException(f"exp_amount must be greater than or equal to 0. exp_amount: {exp_amount}")

        new_total_exp = self.total_exp + exp_amount
        new_level = self.level
        leveled_up = False

        # レベルアップ判定：現在のレベルより高いレベルに到達できるかチェック
        while True:
            required_exp_for_next = self.exp_table.get_required_exp_for_level(new_level + 1)
            if new_total_exp >= required_exp_for_next:
                new_level += 1
                leveled_up = True
            else:
                break

        new_growth = Growth(
            level=new_level,
            total_exp=new_total_exp,
            exp_table=self.exp_table
        )

        return new_growth, leveled_up
