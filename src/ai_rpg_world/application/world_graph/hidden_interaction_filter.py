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

from typing import Any, Iterable, List, Optional, Sequence

from ai_rpg_world.domain.world_graph.enum.interaction_condition_visibility import (
    is_hidden,
)


def is_hidden_from_actor(interaction: Any, player: Optional[Any]) -> bool:
    """役割などの伏せた条件で、この行為者には存在ごと伏せる操作か。

    ``ConditionVisibility.HIDDEN`` の条件が 1 つでも満たされていなければ
    True。呼び出し側は候補からも一覧からも丸ごと落とす。

    対象を特定できない宣言 (``required_state`` が空) は伏せない。ここで
    伏せると、**書き間違いが「候補が出ない」として静かに消える**。判断は
    実行時のガードに任せて表示は残す。
    """
    state: Optional[dict] = None
    for cond in getattr(interaction, "preconditions", ()) or ():
        if not is_hidden(getattr(cond, "condition_type", None)):
            continue
        required = getattr(cond, "required_state", None)
        if not required:
            continue
        if state is None:
            # 伏せる条件が実際に出てくるまで読まない。**先に読むと、
            # 条件を持たない操作しか無い相手でも state を要求してしまう。**
            state = dict(getattr(player, "state", {}) or {}) if player else {}
        if any(state.get(key) != value for key, value in required.items()):
            return True
    return False


def visible_interactions(
    interactions: Iterable[Any], player: Optional[Any]
) -> List[Any]:
    """その行為者に見えている操作だけを、宣言順のまま返す。"""
    return [i for i in interactions if not is_hidden_from_actor(i, player)]


def visible_action_names(
    interactions: Sequence[Any], player: Optional[Any]
) -> List[str]:
    """その行為者に見えている操作の名前だけを返す。

    **行為者が分からないときは空を返す。** 全部を返すと、行為者を渡し
    忘れた経路が「たまたま全部見える」として静かに漏れる。呼び出し側は
    「(なし)」を出すことになるが、**漏らすよりはよい**。
    """
    if player is None:
        return []
    return [
        str(i.action_name)
        for i in visible_interactions(interactions, player)
        if getattr(i, "action_name", None)
    ]


__all__ = [
    "is_hidden_from_actor",
    "visible_action_names",
    "visible_interactions",
]
