from src.domain.player.hp import Hp
from src.domain.player.mp import Mp
from src.domain.player.exp import Exp
from src.domain.player.level import Level
from src.domain.player.gold import Gold


class DynamicStatus:
    """動的なステータスの管理クラス"""
    
    def __init__(
        self,
        hp: Hp,
        mp: Mp,
        exp: Exp,
        level: Level,
        gold: Gold,
        defending: bool = False,
    ):
        self._hp = hp
        self._mp = mp
        self._exp = exp
        self._level = level
        self._gold = gold
        self._defending = defending

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
    def take_damage(self, damage: int):
        """ダメージを受ける"""
        self._hp = self._hp.damage(damage)
    
    def heal(self, amount: int):
        """回復"""
        self._hp = self._hp.heal(amount)
    
    def recover_mp(self, amount: int):
        """MP回復"""
        self._mp = self._mp.heal(amount)
    
    def consume_mp(self, amount: int):
        """MPを消費"""
        self._mp = self._mp.damage(amount)
    
    def can_consume_mp(self, amount: int) -> bool:
        """MPが足りるかどうか"""
        return self._mp.can_consume(amount)

    def is_alive(self) -> bool:
        """生存しているかどうか"""
        return not self._hp.is_dead()
    
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
    
    def defend(self):
        """防御"""
        self._defending = True
    
    def un_defend(self):
        """防御解除"""
        self._defending = False
    
    def is_defending(self) -> bool:
        """防御状態かどうか"""
        return self._defending