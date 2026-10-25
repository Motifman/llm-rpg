from enum import Enum


class ObjectTypeEnum(Enum):
    """相互作用オブジェクトの種類"""
    CHEST = "CHEST"
    DOOR = "DOOR"
    GATE = "GATE"
    SIGN = "SIGN"
    SWITCH = "SWITCH"
    PLAYER = "PLAYER"
    NPC = "NPC"
    RESOURCE = "RESOURCE"
    GROUND_ITEM = "GROUND_ITEM"  # 落ちているアイテム（当たり判定なし・同一座標に複数可）


class SpotCategoryEnum(Enum):
    """スポットのカテゴリ"""
    TOWN = "TOWN"
    VILLAGE = "VILLAGE"
    DUNGEON = "DUNGEON"
    FIELD = "FIELD"
    INN = "INN"
    SHOP = "SHOP"
    QUEST_HUB = "QUEST_HUB"
    SAVE_POINT = "SAVE_POINT"
    OTHER = "OTHER"


class DirectionEnum(Enum):
    """向きの種類"""
    NORTH = "NORTH"
    NORTHEAST = "NORTHEAST"
    SOUTH = "SOUTH"
    SOUTHEAST = "SOUTHEAST"
    EAST = "EAST"
    WEST = "WEST"
    NORTHWEST = "NORTHWEST"
    SOUTHWEST = "SOUTHWEST"
    UP = "UP"
    DOWN = "DOWN"

    def to_2d_vector(self) -> tuple[int, int] | None:
        from ai_rpg_world.domain.world.value_object.facing import Facing

        return Facing.from_direction(self).to_2d_vector()

    @classmethod
    def from_delta(cls, dx: int, dy: int, dz: int = 0) -> "DirectionEnum":
        from ai_rpg_world.domain.world.value_object.facing import Facing

        return Facing.from_delta(dx, dy, dz).to_direction()


class EnvironmentTypeEnum(Enum):
    """環境の種類（天候の影響を左右する）"""
    OUTDOOR = "OUTDOOR"      # 屋外（天候の影響をフルに受ける）
    INDOOR = "INDOOR"        # 屋内（天候の影響を受けない）
    UNDERGROUND = "UNDERGROUND" # 地下（天候の影響を受けず、独自の環境変化がある可能性がある）


class EstablishmentType(Enum):
    """ロケーションに割り当て可能な施設の種類"""
    SHOP = "SHOP"
    GUILD = "GUILD"
    # 将来: WAREHOUSE = "WAREHOUSE", TAVERN = "TAVERN" 等


class SpotTraitEnum(Enum):
    """スポット（マップ）が持つ環境・雰囲気の特性。複数選択可能（タグ）。"""
    FOREST = "FOREST"           # 森
    WATER_EDGE = "WATER_EDGE"   # 水辺
    LAVA = "LAVA"               # 溶岩地帯
    DANGEROUS = "DANGEROUS"     # 危険地帯
    SAFE_ZONE = "SAFE_ZONE"     # 安全地帯
    DUNGEON_DEPTH = "DUNGEON_DEPTH"  # ダンジョン奥
    OPEN_FIELD = "OPEN_FIELD"   # 開けた野原
    OTHER = "OTHER"             # その他
