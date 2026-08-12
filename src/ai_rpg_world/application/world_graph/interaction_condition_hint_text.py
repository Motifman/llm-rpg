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
from ai_rpg_world.domain.world.enum.weather_enum import WeatherTypeEnum
from ai_rpg_world.domain.world_graph.enum.lighting_enum import LightingEnum
from ai_rpg_world.application.world_graph.tool_argument_text import (
    quote_tool_argument,
)

ItemSpecNameResolver = Callable[[object], Optional[str]]
ObjectStateRequirementTextResolver = Callable[[object], Optional[str]]

#: 時刻帯フェーズ名 → シナリオが宣言した呼び名。引けなければ None。
#:
#: **コード側に既定の表を持たない。** `DayNightPhaseDef` は「シナリオ自由命名」で
#: 設計されており、呼び名 (`display_text`) もシナリオが宣言している。コードが表を
#: 持つと二重管理になり、`world_briefing` が直した「写しは腐る」と同じことが起きる。
#: 実際に腐っていた: v3_coop / v4_coop が `predawn`(未明) を宣言しているのに表には
#: 無く、表にある `afternoon` はどのシナリオも宣言していなかった。**両方向にずれて
#: いた。**
TimeOfDayPhaseLabelResolver = Callable[[str], Optional[str]]

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




#: 網羅テストが見る (enum, 表) の組。**表を足したらここにも足す。**
#:
#: `world_vocabulary.DISPLAY_TABLES` と同じ形。あちらは「暗い」、こちらは
#: 「暗い場所」と語尾が違うので表は統合しないが、**キーの集合は一致させる**。
#: 片方にだけ値がある状態は、どちらかが生値を出す側を持つことを意味する。
ENUM_BACKED_LABEL_TABLES: tuple = (
    (WeatherTypeEnum, _WEATHER_TYPE_LABELS),
    (LightingEnum, _LIGHTING_LABELS),
)


def label_weather_type(value: str) -> Optional[str]:
    """天候の呼び名。**知らない値に生値を返さない。**

    以前は `.get(value, value)` で生値へ倒れていた。`world_vocabulary` が
    「enum の生値をプロンプトに出さない」ために作られ、その docstring が
    ``PITCH_BLACK`` だけ生値が出ていた事故を記録しているのに、同じ穴がここに
    残っていた。呼び出し側はヒントごと落とす。
    """
    return _WEATHER_TYPE_LABELS.get(value)


def label_lighting(value: str) -> Optional[str]:
    """明るさの呼び名。**知らない値に生値を返さない。**"""
    return _LIGHTING_LABELS.get(value)


def declarative_condition_hints(
    interaction,
    *,
    item_spec_name_resolver: Optional[ItemSpecNameResolver] = None,
    object_state_requirement_text_resolver: Optional[
        ObjectStateRequirementTextResolver
    ] = None,
    time_of_day_phase_label_resolver: Optional[TimeOfDayPhaseLabelResolver] = None,
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
            time_of_day_phase_label_resolver,
        )
        if text:
            hints.append(text)
    return tuple(hints)


def _time_of_day(cond, _items, _objstate, _phase_label, *, suffix: str) -> Optional[str]:
    """時刻帯のヒント。呼び名はシナリオ宣言から引く。

    resolver が無い / 宣言に無いフェーズなら **ヒントごと落とす**。生値を出すと
    ``"predawnのみ"`` のように内部識別子がプロンプトへ漏れる。
    """
    phase = cond.required_time_of_day_phase
    if not phase or _phase_label is None:
        return None
    label = _phase_label(phase)
    return f"{label}{suffix}" if label else None


def _weather(cond, _items, _objstate, _phase_label, *, suffix: str) -> Optional[str]:
    if not cond.required_weather_type:
        return None
    label = label_weather_type(cond.required_weather_type)
    # 呼び名が引けないならヒントごと落とす。空文字を埋めると "のみ" だけが残り、
    # 生値より読めない断片になる (既存の `_has_item` と同じ判断)。
    return f"{label}{suffix}" if label else None


def _lighting(cond, _items, _objstate, _phase_label, *, suffix: str) -> Optional[str]:
    if not cond.required_lighting:
        return None
    label = label_lighting(cond.required_lighting)
    return f"{label}{suffix}" if label else None


def _has_item(
    cond, item_spec_name_resolver, _objstate, _phase_label, *, suffix: str
) -> Optional[str]:
    if item_spec_name_resolver is None or cond.target_item_spec_id is None:
        return None
    name = item_spec_name_resolver(cond.target_item_spec_id)
    return f"{name}{suffix}" if name else None


def _object_state_int(
    cond, _items, object_state_requirement_text_resolver, _phase_label
):
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
        lambda c, i, o, ph: _time_of_day(c, i, o, ph, suffix="のみ"),
        lambda c, i, o, ph: _time_of_day(c, i, o, ph, suffix="不可"),
    ),
    InteractionConditionTypeEnum.WEATHER_IS: (
        lambda c, i, o, ph: _weather(c, i, o, ph, suffix="のみ"),
        lambda c, i, o, ph: _weather(c, i, o, ph, suffix="不可"),
    ),
    InteractionConditionTypeEnum.SPOT_LIGHTING_IS: (
        lambda c, i, o, ph: _lighting(c, i, o, ph, suffix="のみ"),
        lambda c, i, o, ph: _lighting(c, i, o, ph, suffix="不可"),
    ),
    InteractionConditionTypeEnum.HAS_ITEM: (
        lambda c, i, o, ph: _has_item(c, i, o, ph, suffix="が要る"),
        lambda c, i, o, ph: _has_item(c, i, o, ph, suffix="を持っていると不可"),
    ),
    InteractionConditionTypeEnum.TARGET_HAS_ITEM: (
        lambda c, i, o, ph: _has_item(c, i, o, ph, suffix="を相手が持っていること"),
        lambda c, i, o, ph: _has_item(c, i, o, ph, suffix="を相手が持っていないこと"),
    ),
    InteractionConditionTypeEnum.OBJECT_STATE_INT_AT_LEAST: (
        lambda c, i, o, ph: _object_state_int(c, i, o, ph),
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
