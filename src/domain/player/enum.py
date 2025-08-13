from enum import Enum


class Role(Enum):
    """プレイヤーのロール"""
    CITIZEN = "citizen"          
    ADVENTURER = "adventurer"    
    MERCHANT = "merchant"        
    SHOP_KEEPER = "shop_keeper"  
    TRADER = "trader"            
    CRAFTSMAN = "craftsman"      
    BLACKSMITH = "blacksmith"    
    ALCHEMIST = "alchemist"      
    TAILOR = "tailor"            
    INNKEEPER = "innkeeper"      
    DANCER = "dancer"            
    PRIEST = "priest"            
    FARMER = "farmer"            
    FISHER = "fisher"            
    MINER = "miner"              
    WOODCUTTER = "woodcutter"    


class PlayerState(Enum):
    """プレイヤーの状態"""
    NORMAL = "normal"           # 通常状態
    CONVERSATION = "conversation"  # 会話状態
    SNS = "sns"                # SNS状態
    BATTLE = "battle"          # 戦闘状態
    TRADING = "trading"        # 取引状態


class StatusEffectType(Enum):
    """状態異常"""
    # ダメージを受ける
    POISON = "poison"    
    BURN = "burn"
    # 回復
    BLESSING = "blessing"
    # 行動不能
    PARALYSIS = "paralysis" 
    SLEEP = "sleep"     
    CONFUSION = "confusion" 
    # 魔法攻撃不能
    SILENCE = "silence" 
    # ステータスアップ
    ATTACK_UP = "attack_up"
    DEFENSE_UP = "defense_up"
    SPEED_UP = "speed_up"    
    # ステータスダウン
    ATTACK_DOWN = "attack_down"
    DEFENSE_DOWN = "defense_down"
    SPEED_DOWN = "speed_down"
    # 特殊
    CURSE = "curse"
