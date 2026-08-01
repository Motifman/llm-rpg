"""前提条件を、action 候補の行末に添える短い日本語ヒントに変換する。

物体行の ``採取する (gather・夜のみ)`` と同席者行の
``背後から襲う (strike_down・暗い場所のみ)`` は同じ書式で出す。書式と
語彙が経路ごとにずれると、LLM から見て「同じ意味の表示なのに読み方が違う」
ものが増える。

ここが扱うのは **宣言だけから決まる** 条件に限る (時刻 / 天候 / 明るさ /
所持品)。「今この物体の state が条件を満たしていない」のような実行時の値に
依存するヒントは、材料を持っている呼び出し側 (state builder) が足す。
"""

from __future__ import annotations

from typing import Callable, Optional

from ai_rpg_world.domain.world_graph.enum.interaction_condition_type import (
    InteractionConditionTypeEnum,
)

ItemSpecNameResolver = Callable[[object], Optional[str]]

_TIME_OF_DAY_PHASE_LABELS: dict[str, str] = {
    "morning": "朝",
    "noon": "昼",
    "afternoon": "午後",
    "evening": "夕暮れ",
    "night": "夜",
}

_WEATHER_TYPE_LABELS: dict[str, str] = {
    "CLEAR": "晴れ",
    "CLOUDY": "曇り",
    "RAIN": "雨",
    "HEAVY_RAIN": "大雨",
    "SNOW": "雪",
    "BLIZZARD": "吹雪",
    "FOG": "霧",
    "STORM": "嵐",
}

_LIGHTING_LABELS: dict[str, str] = {
    "BRIGHT": "明るい場所",
    "DIM": "薄暗い場所",
    "DARK": "暗い場所",
    "PITCH_BLACK": "真っ暗な場所",
}


def label_time_of_day_phase(value: str) -> str:
    """時刻帯の内部値を prompt 用の短い日本語へ変換する。未知値はそのまま出す。"""
    return _TIME_OF_DAY_PHASE_LABELS.get(value, value)


def label_weather_type(value: str) -> str:
    """天候の内部値を prompt 用の短い日本語へ変換する。未知値はそのまま出す。"""
    return _WEATHER_TYPE_LABELS.get(value, value)


def label_lighting(value: str) -> str:
    """明るさの内部値を prompt 用の短い日本語へ変換する。未知値はそのまま出す。"""
    return _LIGHTING_LABELS.get(value, value)


def declarative_condition_hints(
    interaction,
    *,
    item_spec_name_resolver: Optional[ItemSpecNameResolver] = None,
) -> tuple[str, ...]:
    """宣言だけから決まる前提条件を、宣言順のヒント列にする。

    ``item_spec_name_resolver`` を渡したときだけ ``HAS_ITEM`` を
    「ナイフが要る」の形で添える。物体行では所持品の不足が remediation に
    出るため重複するので渡さない。対人 action にはその重複が無く、何を持て
    ば成立するのかが失敗するまで prompt のどこにも出ない。

    名前を引けなかった品目は**その条件のヒントだけ落とす**。名前が出せない
    だけで action 候補ごと消すと、宣言した行為が LLM から発見できなくなる。
    """
    hints: list[str] = []
    for cond in interaction.preconditions:
        t = cond.condition_type
        if t == InteractionConditionTypeEnum.TIME_OF_DAY_IS:
            if cond.required_time_of_day_phase:
                hints.append(
                    f"{label_time_of_day_phase(cond.required_time_of_day_phase)}のみ"
                )
            continue
        if t == InteractionConditionTypeEnum.TIME_OF_DAY_IS_NOT:
            if cond.required_time_of_day_phase:
                hints.append(
                    f"{label_time_of_day_phase(cond.required_time_of_day_phase)}不可"
                )
            continue
        if t == InteractionConditionTypeEnum.WEATHER_IS:
            if cond.required_weather_type:
                hints.append(f"{label_weather_type(cond.required_weather_type)}のみ")
            continue
        if t == InteractionConditionTypeEnum.WEATHER_IS_NOT:
            if cond.required_weather_type:
                hints.append(f"{label_weather_type(cond.required_weather_type)}不可")
            continue
        if t == InteractionConditionTypeEnum.SPOT_LIGHTING_IS:
            if cond.required_lighting:
                hints.append(f"{label_lighting(cond.required_lighting)}のみ")
            continue
        if t == InteractionConditionTypeEnum.SPOT_LIGHTING_IS_NOT:
            if cond.required_lighting:
                hints.append(f"{label_lighting(cond.required_lighting)}不可")
            continue
        if t == InteractionConditionTypeEnum.HAS_ITEM:
            if item_spec_name_resolver is None or cond.target_item_spec_id is None:
                continue
            name = item_spec_name_resolver(cond.target_item_spec_id)
            if name:
                hints.append(f"{name}が要る")
            continue
    return tuple(hints)


def format_action_display_with_hints(
    action_name: str,
    hints,
    *,
    display_label: str = "",
) -> str:
    """action の意味ラベル・識別子・ヒントを含む**表示用**文字列を作る。

    戻り値は識別子ではない。executor が「使える操作」を列挙する経路には
    素の action_name を渡すこと。装飾込みの文字列を出すと、LLM が
    ``背後から襲う (strike_down・暗い場所のみ)`` をそのまま action_name として渡し、
    「そんな操作は無い」の往復になる。
    """
    rendered = tuple(str(h).strip() for h in (hints or ()) if str(h).strip())
    label = str(display_label or "").strip()
    if label:
        inside = "・".join((action_name, *rendered))
        return f"{label} ({inside})"
    if not rendered:
        return action_name
    return f"{action_name}({'・'.join(rendered)})"
