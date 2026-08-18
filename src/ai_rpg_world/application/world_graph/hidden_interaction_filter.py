"""行為者に伏せる操作を、1 か所で判断する。

## なぜ 1 か所に集めるか

判断は既にあった。``spot_graph_current_state_builder`` が、役割で弾かれる
候補を候補一覧から**行ごと**落としている。「いまできない」に回すだけでは
**その操作が存在すること**が伝わってしまうためで、偽装版 (``_pretend``) の
仕組みはこの隠蔽の上に成り立っている。

その判断が、**もう 1 か所では抜けていた**。操作名を間違えたときの救済
メッセージが、そのオブジェクトの全操作をそのまま並べていた。

    このオブジェクトには 'examine' という操作がありません。
    利用可能な操作: log_weather, log_weather_2, log_weather_3, log_weather_pretend

実 run 011 で、この漏れは**実際に使われた**。

    t24 ハギ (クルー) が別の操作名を間違える
         → 一覧に count_supplies_pretend が出る
    t26 ハギが count_supplies_pretend を呼ぶ
    t28 ハギが別のオブジェクトに check_generator_pretend を呼ぶ

**偽装版という仕組みそのものを学習している。** クルーがこれを知る手段は
本来無い。片側で行ごと消しておきながら、隣で名前を教えていた。

これは今週 5 回踏んだ「判断が散ると忘れられる」と同じ形 (``ToolExposure``
#922 / 死の到達範囲 #946 / dispatch のガード #948 / 節の並び #950)。
同じ直し方をする。**一覧を作る側は必ずここを通る。**

## 救済そのものは残す

一覧を消してしまうと、``examine`` のような発明された名前から正しい名前へ
戻る道が無くなる。実 run 011 で 12 件がこの救済に助けられている。
**消すのではなく、その人に見えている操作だけを並べる。**
"""

from __future__ import annotations

from typing import Any, Iterable, List, Mapping, Optional, Sequence

from ai_rpg_world.domain.world_graph.enum.interaction_condition_visibility import (
    is_hidden,
)
from ai_rpg_world.domain.world_graph.enum.interaction_condition_type import (
    InteractionConditionTypeEnum,
)
from ai_rpg_world.domain.world_graph.enum.interaction_actor_plane import (
    InteractionActorPlane,
)

#: 伏せる条件のうち、**行為者自身**について訊いているもの。
#:
#: ここに載せてよいのは「その人が自分について知っている事実」だけ。
#: ``TARGET_PLAYER_STATE_IS`` のような**相手**について訊く条件を入れては
#: いけない。入れると、相手の伏せた役割で一覧の中身が変わり、**誰が
#: どちら側かが読めてしまう**。
#:
#: ``available_action_entries_for`` の ``_actor_meets_own_state_conditions``
#: が同じ規則を明文化している。判断を 1 か所に集める過程で、うっかり
#: 相手側の条件まで行為者の state で判定しかけた。網羅テストが縛る。
_ACTOR_SCOPED_HIDDEN = frozenset({InteractionConditionTypeEnum.PLAYER_STATE_IS})


def _is_actor_scoped_hidden(condition_type: Any) -> bool:
    """行為者自身の state で判定してよい、伏せる条件か。"""
    return condition_type in _ACTOR_SCOPED_HIDDEN and is_hidden(condition_type)


def is_hidden_from_state(
    interaction: Any, actor_state: Optional[Mapping[str, Any]]
) -> bool:
    """行為者の自由 state を直接渡す入口。

    ``ConditionVisibility.HIDDEN`` の条件が 1 つでも満たされていなければ
    True。呼び出し側は候補からも一覧からも失敗観測からも丸ごと落とす。

    対象を特定できない宣言 (``required_state`` が空) は伏せない。ここで
    伏せると、**書き間違いが「候補が出ない」として静かに消える**。判断は
    実行時のガードに任せて表示は残す。

    ``actor_state`` が ``None`` のときは空として扱う = すべて伏せる側へ
    倒れる。**分からないなら見せない。**
    """
    return bool(_failed_actor_hidden_conditions(interaction, actor_state))


def _failed_actor_hidden_conditions(
    interaction: Any, actor_state: Optional[Mapping[str, Any]]
) -> List[Any]:
    """行為者自身の state が満たしていない伏せた条件を返す。"""
    state = dict(actor_state or {})
    failed: List[Any] = []
    for cond in getattr(interaction, "preconditions", ()) or ():
        if not _is_actor_scoped_hidden(getattr(cond, "condition_type", None)):
            continue
        required = getattr(cond, "required_state", None)
        if not required:
            continue
        if any(state.get(key) != value for key, value in required.items()):
            failed.append(cond)
    return failed


def failed_actor_hidden_requirements(
    interaction: Any, actor_state: Optional[Mapping[str, Any]]
) -> List[Mapping[str, Any]]:
    """満たしていない伏せた条件が、**何を要求しているか**を宣言順に返す。

    ``hidden_failure_messages_from_state`` が作者の文面を返すのに対し、
    こちらは要求そのもの (``{"trade": "baker"}``) を返す。呼んだ人ひとりへの
    応答と、一覧に常時出る注記とでは、**要る形が違う**ためである。文面は
    「あなたには無理だ」で完結してよいが、注記は「では誰なら」に答える位置に
    いるので、engine 側で組み直せる形が要る。
    """
    return [
        dict(getattr(cond, "required_state", None) or {})
        for cond in _failed_actor_hidden_conditions(interaction, actor_state)
    ]


def hidden_failure_messages_from_state(
    interaction: Any, actor_state: Optional[Mapping[str, Any]]
) -> List[str]:
    """伏せた操作名を明かさず、宣言済みの不成立理由だけを返す。

    候補一覧から操作を落としても、対象物まで「存在しない」と扱ってはいけない。
    ``failure_message`` は、正しい操作名を知って呼んだ場合にも domain が本人へ
    返す理由なので、ここで同じ文を使っても秘密の操作名は増えない。
    """
    messages: List[str] = []
    for cond in _failed_actor_hidden_conditions(interaction, actor_state):
        message = str(getattr(cond, "failure_message", "") or "").strip()
        if message and message not in messages:
            messages.append(message)
    return messages


def is_hidden_from_actor(
    interaction: Any,
    player: Optional[Any],
    world_flags: Optional[frozenset[str]] = None,
) -> bool:
    """行為者の集約と世界フラグを渡し、操作の存在を伏せるか返す。

    行為者の自由 state と、作者が明示した世界フラグ前提だけを扱う。世界
    フラグは時限ギミックの解禁・終了を表し、明示がない既存操作は従来どおり
    不成立理由つきで残す。

    ``player`` から ``state`` を読むのは、**伏せる条件が実際に出てきてから**。
    先に読むと、条件を 1 つも持たない操作しか無い場面でも state を要求する。
    """
    if _has_failed_hidden_flag_precondition(interaction, world_flags):
        return True
    if not _has_hidden_actor_state_precondition(interaction):
        return False
    return is_hidden_from_state(
        interaction, getattr(player, "state", None) if player is not None else None
    )


def _has_hidden_actor_state_precondition(interaction: Any) -> bool:
    """伏せる条件を 1 つでも宣言しているか。"""
    return any(
        _is_actor_scoped_hidden(getattr(cond, "condition_type", None))
        and getattr(cond, "required_state", None)
        for cond in getattr(interaction, "preconditions", ()) or ()
    )


def _has_failed_hidden_flag_precondition(
    interaction: Any,
    world_flags: Optional[frozenset[str]],
) -> bool:
    """世界フラグで解禁・終了する操作を、不成立中は候補ごと伏せる。"""
    if not bool(getattr(interaction, "hide_when_flag_preconditions_fail", False)):
        return False
    flags = world_flags or frozenset()
    for cond in getattr(interaction, "preconditions", ()) or ():
        condition_type = getattr(cond, "condition_type", None)
        flag_name = getattr(cond, "flag_name", None)
        if condition_type is InteractionConditionTypeEnum.FLAG_SET:
            if not flag_name or flag_name not in flags:
                return True
        elif condition_type is InteractionConditionTypeEnum.FLAG_NOT_SET:
            if not flag_name or flag_name in flags:
                return True
    return False


def visible_interactions(
    interactions: Iterable[Any],
    player: Optional[Any],
    world_flags: Optional[frozenset[str]] = None,
) -> List[Any]:
    """その行為者に見えている操作だけを、宣言順のまま返す。"""
    return [
        i for i in interactions
        if not is_hidden_from_actor(i, player, world_flags)
    ]


def visible_interactions_for_actor_plane(
    interactions: Iterable[Any],
    player: Optional[Any],
    world_flags: Optional[frozenset[str]],
    actor_plane: InteractionActorPlane,
) -> List[Any]:
    """役割・世界状態・存在層のすべてで本人に見える操作だけを返す。

    候補表示と、名前を誤ったときの救済一覧はこの同じ集合を使う。片側だけ
    ``allows_actor_plane`` を忘れると、候補で伏せた生者専用操作を幽霊へ
    エラー文から教えてしまうためである。
    """
    return [
        interaction
        for interaction in visible_interactions(interactions, player, world_flags)
        if interaction.allows_actor_plane(actor_plane)
    ]


def visible_action_names(
    interactions: Sequence[Any],
    player: Optional[Any],
    world_flags: Optional[frozenset[str]] = None,
) -> List[str]:
    """その行為者に見えている操作の名前だけを返す。

    **行為者が分からないときは空を返す。** 全部を返すと、行為者を渡し
    忘れた経路が「たまたま全部見える」として静かに漏れる。

    ただしこれは最後の砦であって、**渡し忘れを防ぐのは引数の必須化のほう**。
    空になるのもそれはそれで静かな失敗で、案内が丸ごと死んだことに誰も
    気づけない。呼び出し側は ``player_id`` を必須で受け取ること。
    """
    if player is None:
        return []
    return _names(visible_interactions(interactions, player, world_flags))


def visible_action_names_for_state(
    interactions: Sequence[Any], actor_state: Optional[Mapping[str, Any]]
) -> List[str]:
    """行為者の自由 state から、見えている操作の名前だけを返す。

    対人行為の一覧はこちらを使う。``PlayerStatusAggregate`` を持たない
    経路 (domain service の内側) でも同じ判断を通せるようにするため。
    """
    return _names(
        i for i in interactions if not is_hidden_from_state(i, actor_state)
    )


def _names(interactions: Iterable[Any]) -> List[str]:
    return [
        str(i.action_name)
        for i in interactions
        if getattr(i, "action_name", None)
    ]


__all__ = [
    "is_hidden_from_actor",
    "is_hidden_from_state",
    "failed_actor_hidden_requirements",
    "hidden_failure_messages_from_state",
    "visible_action_names",
    "visible_action_names_for_state",
    "visible_interactions",
    "visible_interactions_for_actor_plane",
]
