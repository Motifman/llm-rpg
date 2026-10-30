"""世界の側の乱数を、シードと回の番号と用途から作る (#1514)。

用途ごとに別の乱数にして、ある用途で引く回数が変わっても、ほかの用途の
並びがずれないようにする。1 回目の条件判定と天候は、回の番号を入れる前と
同じ種にして、既存の run を再現できるようにする。2 回目以降は回の番号を
混ぜ、同じ profile で回を重ねても確率の出来事が回ごとに変わるようにする。
"""

from __future__ import annotations

import random


def world_random(seed: int | None, round_number: int, purpose: str) -> random.Random:
    if seed is None:
        return random.Random()
    if round_number == 1:
        if purpose == "scenario":
            return random.Random(seed)
        return random.Random(f"{purpose}:{seed}")
    return random.Random(f"{purpose}:{seed}:round{round_number}")


__all__ = ["world_random"]
