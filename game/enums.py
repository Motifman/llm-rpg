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


class TradeType(Enum):
    GLOBAL = "global"     # グローバル取引所
    DIRECT = "direct"     # 直接取引（同一Spot）


class TradeStatus(Enum):
    ACTIVE = "active"         # 募集中
    COMPLETED = "completed"   # 成立
    CANCELLED = "cancelled"   # キャンセル


class QuestType(Enum):
    """クエストタイプ"""
    MONSTER_HUNT = "monster_hunt"      # モンスター討伐
    ITEM_COLLECTION = "item_collection" # アイテム収集
    EXPLORATION = "exploration"         # 探索
    DELIVERY = "delivery"              # 配達
    RESCUE = "rescue"                  # 救出
    CUSTOM = "custom"                  # カスタム（その他）


class QuestStatus(Enum):
    """クエストステータス"""
    AVAILABLE = "available"    # 受注可能
    ACCEPTED = "accepted"      # 受注済み
    IN_PROGRESS = "in_progress" # 進行中
    COMPLETED = "completed"    # 完了
    FAILED = "failed"          # 失敗
    CANCELLED = "cancelled"    # キャンセル済み


class QuestDifficulty(Enum):
    """クエスト危険度"""
    E = "E"  # 初心者向け
    D = "D"  # 易しい
    C = "C"  # 普通
    B = "B"  # 難しい
    A = "A"  # とても難しい
    S = "S"  # 極めて危険


class GuildRank(Enum):
    """ギルドランク"""
    F = "F"  # 初心者
    E = "E"  # 新人
    D = "D"  # 一般
    C = "C"  # 上級
    B = "B"  # エキスパート
    A = "A"  # ベテラン
    S = "S"  # マスター


class BattleState(Enum):
    """戦闘状態"""
    ACTIVE = "active"       # 戦闘中
    FINISHED = "finished"   # 戦闘終了
    ESCAPED = "escaped"     # 逃走による終了


class TurnActionType(Enum):
    """ターン中の行動タイプ"""
    ATTACK = "attack"
    DEFEND = "defend"
    ESCAPE = "escape"
    MONSTER_ACTION = "monster_action"
    STATUS_EFFECT = "status_effect"


class PlayerState(Enum):
    """プレイヤーの状態"""
    NORMAL = "normal"           # 通常状態
    CONVERSATION = "conversation"  # 会話状態
    SNS = "sns"                # SNS状態
    BATTLE = "battle"          # 戦闘状態
    TRADING = "trading"        # 取引状態