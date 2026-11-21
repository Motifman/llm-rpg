from __future__ import annotations

from enum import Enum


class NotPerceivedReason(Enum):
    ELSEWHERE = "elsewhere"
    OUT_OF_EARSHOT = "out_of_earshot"
    TOO_QUIET = "too_quiet"
    TOO_DARK = "too_dark"
    STEALTH_UNNOTICED = "stealth_unnoticed"
    ACTOR_UNSEEN = "actor_unseen"
    UNCONSCIOUS = "unconscious"
    NOT_OWN_BODY = "not_own_body"
    NOT_ADDRESSED = "not_addressed"
    LEFT_THE_WORLD = "left_the_world"
    DEAD = "dead"
    ALREADY_PERCEIVED = "already_perceived"
