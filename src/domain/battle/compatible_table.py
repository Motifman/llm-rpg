from src.domain.battle.battle_enum import Element


NORMAL_MULTIPLIER = 1.0
STRONG_MULTIPLIER = 1.5
WEAK_MULTIPLIER = 0.5
INVALID_MULTIPLIER = 0.0


# 属性相性テーブル
# キー: (攻撃属性, 防御属性)
# 例: (Element.FIRE, Element.GRASS) は「火が草に強い」
COMPATIBLE_TABLE = {
    # 基本の4元素
    (Element.FIRE, Element.GRASS): STRONG_MULTIPLIER,
    (Element.FIRE, Element.ICE): STRONG_MULTIPLIER,
    (Element.FIRE, Element.WIND): STRONG_MULTIPLIER,
    (Element.FIRE, Element.WATER): WEAK_MULTIPLIER,
    (Element.FIRE, Element.EARTH): WEAK_MULTIPLIER,

    (Element.WATER, Element.FIRE): STRONG_MULTIPLIER,
    (Element.WATER, Element.EARTH): STRONG_MULTIPLIER,
    (Element.WATER, Element.THUNDER): WEAK_MULTIPLIER,
    (Element.WATER, Element.ICE): WEAK_MULTIPLIER,
    (Element.WATER, Element.GRASS): WEAK_MULTIPLIER,

    (Element.THUNDER, Element.WATER): STRONG_MULTIPLIER,
    (Element.THUNDER, Element.WIND): STRONG_MULTIPLIER,
    (Element.THUNDER, Element.EARTH): WEAK_MULTIPLIER,

    (Element.WIND, Element.EARTH): STRONG_MULTIPLIER,
    (Element.WIND, Element.THUNDER): STRONG_MULTIPLIER,
    (Element.WIND, Element.FIRE): WEAK_MULTIPLIER,
    (Element.WIND, Element.ICE): WEAK_MULTIPLIER,

    # 拡張した属性
    (Element.ICE, Element.FIRE): STRONG_MULTIPLIER,
    (Element.ICE, Element.THUNDER): WEAK_MULTIPLIER,
    (Element.ICE, Element.WATER): WEAK_MULTIPLIER,
    (Element.ICE, Element.GRASS): WEAK_MULTIPLIER,

    (Element.EARTH, Element.THUNDER): STRONG_MULTIPLIER,
    (Element.EARTH, Element.POISON): STRONG_MULTIPLIER,
    (Element.EARTH, Element.WIND): STRONG_MULTIPLIER,
    (Element.EARTH, Element.WATER): WEAK_MULTIPLIER,
    (Element.EARTH, Element.GRASS): WEAK_MULTIPLIER,
    (Element.EARTH, Element.FIRE): WEAK_MULTIPLIER,

    (Element.GRASS, Element.WATER): STRONG_MULTIPLIER,
    (Element.GRASS, Element.EARTH): STRONG_MULTIPLIER,
    (Element.GRASS, Element.FIRE): WEAK_MULTIPLIER,
    (Element.GRASS, Element.ICE): WEAK_MULTIPLIER,
    (Element.GRASS, Element.POISON): WEAK_MULTIPLIER,
    (Element.GRASS, Element.WIND): WEAK_MULTIPLIER,

    # 光と闇
    (Element.LIGHT, Element.DARKNESS): STRONG_MULTIPLIER,
    (Element.DARKNESS, Element.LIGHT): STRONG_MULTIPLIER,
}