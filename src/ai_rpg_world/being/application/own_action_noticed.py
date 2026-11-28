from __future__ import annotations

from ai_rpg_world.being.contract import UNKNOWN, Observation, ObservedTime, OwnAction


def own_action_noticed(body: str, time: ObservedTime) -> Observation:
    """Being 自身が返す、自分の 1 手について本人が知ったこと (思い出した本文、出していないツールを呼んだこと)。"""
    return Observation(
        body=body,
        route=OwnAction(),
        time=time,
        subject_is_self=True,
        subject_name=UNKNOWN,
        source=UNKNOWN,
        place=UNKNOWN,
        addressed_to_self=True,
    )


__all__ = ["own_action_noticed"]
