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


class Race(Enum):
    """種族"""
    HUMAN = "human"
    GHOST = "ghost"
    GOBLIN = "goblin"
    ORC = "orc"
    TROLL = "troll"
    TITAN = "titan"
    WEREWOLF = "werewolf"
    WITCH = "witch"
    WIZARD = "wizard"
    WOLF = "wolf"
    ZOMBIE = "zombie"
    DRAGON = "dragon"
    BEAST = "beast"


class Element(Enum):
    """属性"""
    FIRE = "fire"
    WATER = "water"
    THUNDER = "thunder"
    WIND = "wind"
    ICE = "ice"
    EARTH = "earth"
    GRASS = "grass"
    LIGHT = "light"
    DARKNESS = "darkness"
    NEUTRAL = "neutral"
    POISON = "poison"


class PlayerState(Enum):
    """プレイヤーの状態"""
    NORMAL = "normal"           # 通常状態
    CONVERSATION = "conversation"  # 会話状態
    SNS = "sns"                # SNS状態
    BATTLE = "battle"          # 戦闘状態
    TRADING = "trading"        # 取引状態