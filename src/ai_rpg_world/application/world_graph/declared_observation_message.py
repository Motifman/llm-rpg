from __future__ import annotations

from typing import Any, Optional

from ai_rpg_world.domain.world_graph.enum.lighting_enum import LightingEnum
from ai_rpg_world.domain.world.value_object.spot_id import SpotId


def declared_observation_message_for_lighting(
    spot_id: SpotId,
    *,
    resolver: Optional[Any],
    bright: Optional[str],
    dark: Optional[str],
) -> Optional[str]:
    """実効照明に合う宣言文を選び、照明不明時は暗所文へ倒す。

    明所文を暗所で使うと、作者が伏せた行為者名を漏らしうる。したがって
    ``BRIGHT`` と ``DIM`` だけを明所として列挙し、未解決や将来追加される値を
    含む残りは暗所文へ倒す。現在の明所集合は
    ``SpotPerceptionService.can_see_objects`` と同じだが、観測文の身元を伏せるかと
    物体を視認できるかは別の問いである。片方の閾値を変えるときは、もう片方も
    意図的に見直すこと。

    暗所文を宣言していない既存 interaction は明所文をそのまま使い、従来の
    挙動を保つ。
    """
    if bright is None and dark is None:
        return None
    lighting = resolver.resolve(spot_id) if resolver is not None else None
    is_dark = lighting not in (LightingEnum.BRIGHT, LightingEnum.DIM)
    if is_dark:
        return dark if dark is not None else bright
    return bright if bright is not None else dark
