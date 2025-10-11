from enum import Enum


class EquipmentSlotType(Enum):
    """装備スロットの種類

    プレイヤーが装備できるスロットの種類を定義する。
    各スロットは特定の装備アイテムタイプを受け入れる。
    """
    WEAPON = "weapon"
    HELMET = "helmet"
    ARMOR = "armor"
    SHIELD = "shield"
    ACCESSORY = "accessory"
    BOOTS = "boots"
