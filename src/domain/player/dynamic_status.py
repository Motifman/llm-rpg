from src.domain.player.hp import Hp
from src.domain.player.mp import Mp
from src.domain.common.value_object import Exp, Gold, Level


class DynamicStatus:
    """動的なステータスの管理クラス"""
    
    def __init__(
        self,
        hp: Hp,
        mp: Mp,
        exp: Exp,
        level: Level,
        gold: Gold,
    ):
        self._hp = hp
        self._mp = mp
        self._exp = exp
        self._level = level
        self._gold = gold

    @classmethod
    def new_game(cls, max_hp: int, max_mp: int, max_exp: int, initial_level: int) -> 'DynamicStatus':
        """新しいゲームを開始するときの初期ステータスを生成する"""
        hp = Hp(value=max_hp, max_hp=max_hp)
        mp = Mp(value=max_mp, max_mp=max_mp)
        exp = Exp(value=0, max_exp=max_exp)
        level = Level(value=initial_level)
        gold = Gold(value=0)
        
        return cls(hp, mp, exp, level, gold)

    # == ビジネスロジックの実装 ==
    def receive_gold(self, gold: Gold):
        """所持金を追加"""
        self._gold = self._gold + gold
    
    def pay_gold(self, gold: Gold):
        """所持金を支払う"""
        self._gold = self._gold - gold
    
    def can_pay_gold(self, gold: Gold) -> bool:
        """所持金が足りるかどうか"""
        return self._gold >= gold
    
    def receive_exp(self, exp: Exp):
        """経験値を追加"""
        self._exp = self._exp + exp
    
    def pay_exp(self, exp: Exp):
        """経験値を支払う"""
        self._exp = self._exp - exp
    
    def can_pay_exp(self, exp: Exp) -> bool:
        """経験値が足りるかどうか"""
        return self._exp >= exp
    
    def level_up(self):
        """レベルアップ"""
        self._level = self._level.up()
    
    def level_is_above(self, level: Level) -> bool:
        """指定したレベルより上かどうか"""
        return self._level >= level