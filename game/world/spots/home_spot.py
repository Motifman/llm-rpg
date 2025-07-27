from game.world.special_spot import SpecialSpot
from game.enums import Permission
from game.action.actions.home_action import SleepActionStrategy, WriteDiaryActionStrategy


class HomeSpot(SpecialSpot):
    """家のSpot - ベッドでの睡眠、机での日記書き込みが可能"""
    
    def __init__(self, spot_id: str, owner_id: str):
        super().__init__(spot_id, "家", "あなたの家です。ベッドと机があります。")
        
        # オーナーの権限を設定
        self.set_player_permission(owner_id, Permission.OWNER)
        
        # 権限別アクションを定義
        self.add_permission_action(Permission.OWNER, ["睡眠", "日記を書く"])
        
        # Spot固有のActionStrategyを追加
        self.add_action(SleepActionStrategy())
        self.add_action(WriteDiaryActionStrategy()) 