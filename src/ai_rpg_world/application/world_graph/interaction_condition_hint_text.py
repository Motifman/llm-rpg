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
from ai_rpg_world.domain.world_graph.enum.interaction_effect_type import (
    InteractionEffectTypeEnum,
)
from ai_rpg_world.application.world_graph.tool_argument_text import (
    quote_tool_argument,
)

ItemSpecNameResolver = Callable[[object], Optional[str]]
ObjectStateRequirementTextResolver = Callable[[object], Optional[str]]

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
    object_state_requirement_text_resolver: Optional[
        ObjectStateRequirementTextResolver
    ] = None,
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
        renderers = _HINT_RENDERERS.get(cond.condition_type)
        if renderers is None:
            continue
        render, _negative = renderers
        if render is None:
            continue
        text = render(
            cond,
            item_spec_name_resolver,
            object_state_requirement_text_resolver,
        )
        if text:
            hints.append(text)
    return tuple(hints)


def _time_of_day(cond, _items, _objstate, *, suffix: str) -> Optional[str]:
    if not cond.required_time_of_day_phase:
        return None
    return f"{label_time_of_day_phase(cond.required_time_of_day_phase)}{suffix}"


def _weather(cond, _items, _objstate, *, suffix: str) -> Optional[str]:
    if not cond.required_weather_type:
        return None
    return f"{label_weather_type(cond.required_weather_type)}{suffix}"


def _lighting(cond, _items, _objstate, *, suffix: str) -> Optional[str]:
    if not cond.required_lighting:
        return None
    return f"{label_lighting(cond.required_lighting)}{suffix}"


def _has_item(cond, item_spec_name_resolver, _objstate, *, suffix: str) -> Optional[str]:
    if item_spec_name_resolver is None or cond.target_item_spec_id is None:
        return None
    name = item_spec_name_resolver(cond.target_item_spec_id)
    return f"{name}{suffix}" if name else None


def _object_state_int(cond, _items, object_state_requirement_text_resolver, **_):
    text = (
        object_state_requirement_text_resolver(cond)
        if object_state_requirement_text_resolver is not None
        else None
    )
    if text:
        return text
    return f"対象の蓄積が{max(1, int(cond.required_quantity))}以上必要"


#: 条件の種別 → (肯定のときの文, 否定のときの文)。
#:
#: **否定の文は肯定の機械的な反転ではない** (「朝のみ」に対して「朝不可」)。
#: だから分岐の中で `negate` を読む形にはしない。読む形にすると、書き忘れた
#: 分岐は否定を無視して肯定の文を出す。**出ないのではなく嘘が出る。**
#: v4 の「夜不可・嵐不可」が「夜のみ・嵐のみ」と表示された実例がある
#: (この表を入れる前の実装で、既存テストが捕まえた)。
#:
#: `None` は「その組み合わせではヒントを出さない」。表に載っていない種別は
#: `_NO_HINT_CONDITIONS` に理由と共に列挙する。どちらにも無い種別があれば
#: `test_interaction_condition_hint_table.py` が落ちる。
#: 否定専用の種別 → 対になる肯定側の種別。表の組み立てにだけ使う。
_LEGACY_NEGATED_PAIRS = {
    InteractionConditionTypeEnum.TIME_OF_DAY_IS_NOT:
        InteractionConditionTypeEnum.TIME_OF_DAY_IS,
    InteractionConditionTypeEnum.WEATHER_IS_NOT:
        InteractionConditionTypeEnum.WEATHER_IS,
    InteractionConditionTypeEnum.SPOT_LIGHTING_IS_NOT:
        InteractionConditionTypeEnum.SPOT_LIGHTING_IS,
    InteractionConditionTypeEnum.AT_SPOT_IS_NOT:
        InteractionConditionTypeEnum.AT_SPOT_IS,
    InteractionConditionTypeEnum.TARGET_HAS_NO_ITEM:
        InteractionConditionTypeEnum.TARGET_HAS_ITEM,
}

_HINT_RENDERERS: dict = {
    InteractionConditionTypeEnum.TIME_OF_DAY_IS: (
        lambda c, i, o: _time_of_day(c, i, o, suffix="のみ"),
        lambda c, i, o: _time_of_day(c, i, o, suffix="不可"),
    ),
    InteractionConditionTypeEnum.WEATHER_IS: (
        lambda c, i, o: _weather(c, i, o, suffix="のみ"),
        lambda c, i, o: _weather(c, i, o, suffix="不可"),
    ),
    InteractionConditionTypeEnum.SPOT_LIGHTING_IS: (
        lambda c, i, o: _lighting(c, i, o, suffix="のみ"),
        lambda c, i, o: _lighting(c, i, o, suffix="不可"),
    ),
    InteractionConditionTypeEnum.HAS_ITEM: (
        lambda c, i, o: _has_item(c, i, o, suffix="が要る"),
        lambda c, i, o: _has_item(c, i, o, suffix="を持っていると不可"),
    ),
    InteractionConditionTypeEnum.TARGET_HAS_ITEM: (
        lambda c, i, o: _has_item(c, i, o, suffix="を相手が持っていること"),
        lambda c, i, o: _has_item(c, i, o, suffix="を相手が持っていないこと"),
    ),
    InteractionConditionTypeEnum.OBJECT_STATE_INT_AT_LEAST: (
        _object_state_int,
        None,
    ),
}

# 否定専用の種別は、否定の文を「肯定側」として持つ。
#
# 表の 2 列目は将来 negate を入れるときの置き場として空けてある。いまは
# 種別が別々なので 1 列目だけを使う。
for _legacy, _base in _LEGACY_NEGATED_PAIRS.items():
    _renderers = _HINT_RENDERERS.get(_base)
    if _renderers is not None and _renderers[1] is not None:
        _HINT_RENDERERS[_legacy] = (_renderers[1], None)


def required_parameter_hints(interaction) -> tuple[str, ...]:
    """effect 宣言が必須にする interaction parameter を表示用ヒントにする。

    ``WRITE_PLAYER_TEXT`` の実行側と同じく ``text_param_key`` の既定値は
    ``text``。同じキーを要求する effect が複数あっても表示は一度にする。
    """
    hints: list[str] = []
    for effect in interaction.effects:
        if effect.effect_type != InteractionEffectTypeEnum.WRITE_PLAYER_TEXT:
            continue
        raw_key = effect.parameters.get("text_param_key", "text")
        if not isinstance(raw_key, str) or not raw_key.strip():
            continue
        hint = f"{quote_tool_argument(raw_key.strip())} が要る"
        if hint not in hints:
            hints.append(hint)
    return tuple(hints)


def format_action_display_with_hints(
    action_name: str,
    hints,
    *,
    display_label: str = "",
) -> str:
    """action の意味ラベル・識別子・ヒントを含む**表示用**文字列を作る。

    戻り値は識別子ではない。executor が「使える操作」を列挙する経路には
    素の action_name を渡すこと。prompt 上では、意味を示す label と
    tool にそのまま渡す値を矢印で分け、後者だけを引用符で囲む。
    """
    rendered = tuple(str(h).strip() for h in (hints or ()) if str(h).strip())
    label = str(display_label or "").strip()
    argument = quote_tool_argument(action_name)
    hint_suffix = f"（{'・'.join(rendered)}）" if rendered else ""
    if label:
        return f"{label} → {argument}{hint_suffix}"
    return f"{argument}{hint_suffix}"
