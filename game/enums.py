from enum import Enum


class Element(Enum):
    """属性"""
    FIRE = "fire"     
    ICE = "ice"       
    THUNDER = "thunder" 
    HOLY = "holy"     
    DARK = "dark"     
    PHYSICAL = "physical" 


class Race(Enum):
    """種族"""
    HUMAN = "human"
    MONSTER = "monster"
    UNDEAD = "undead"
    DRAGON = "dragon"
    BEAST = "beast"
    DEMON = "demon"


class StatusEffectType(Enum):
    """状態異常"""
    POISON = "poison"    
    PARALYSIS = "paralysis" 
    SLEEP = "sleep"     
    CONFUSION = "confusion" 
    SILENCE = "silence" 
    ATTACK_UP = "attack_up"
    DEFENSE_UP = "defense_up"
    SPEED_UP = "speed_up"    


class DamageType(Enum):
    """ダメージタイプ"""
    PHYSICAL = "physical" 
    MAGICAL = "magical" 


class WeaponType(Enum):
    """武器タイプ"""
    SWORD = "sword"   
    BOW = "bow"       
    AXE = "axe"       
    HAMMER = "hammer" 


class ArmorType(Enum):
    """防具タイプ"""
    HELMET = "helmet"   
    CHEST = "chest"     
    SHOES = "shoes"     
    GLOVES = "gloves"   


class EquipmentSlot(Enum):
    """装備スロット（統一的な装備管理用）"""
    WEAPON = "weapon"
    HELMET = "helmet"
    CHEST = "chest"
    SHOES = "shoes"
    GLOVES = "gloves"


class MonsterType(Enum):
    """モンスターのタイプ"""
    NORMAL = "normal"
    AGGRESSIVE = "aggressive"
    HIDDEN = "hidden"
    PASSIVE = "passive"


class Permission(Enum):
    OWNER = "owner"          
    EMPLOYEE = "employee"    
    CUSTOMER = "customer"    
    MEMBER = "member"        
    GUEST = "guest"          
    DENIED = "denied"        


class Role(Enum):
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


class NotificationType(Enum):
    FOLLOW = "follow"
    LIKE = "like"
    REPLY = "reply"
    MENTION = "mention"


class PostVisibility(Enum):
    PUBLIC = "public"                    # 全ユーザーが閲覧可能
    FOLLOWERS_ONLY = "followers_only"    # フォロワーのみ閲覧可能
    MUTUAL_FOLLOWS_ONLY = "mutual_follows_only"  # 相互フォローのみ閲覧可能
    SPECIFIED_USERS = "specified_users"  # 指定ユーザーのみ閲覧可能
    PRIVATE = "private"                  # 本人のみ閲覧可能

