"""プレイヤーの終局結果を観測文へ変換する。"""

from __future__ import annotations

from typing import Mapping, Optional

from ai_rpg_world.domain.player.enum.player_outcome_enum import PlayerOutcomeEnum


_DEFAULT_TEMPLATES: Mapping[PlayerOutcomeEnum, str] = {
    PlayerOutcomeEnum.DEAD: "{player_name}は死亡した。もう蘇生できない。",
    PlayerOutcomeEnum.EJECTED: "{player_name}は投票で追放された。もう戻らない。",
    PlayerOutcomeEnum.RESCUED: "{player_name}は救助された。",
    PlayerOutcomeEnum.STRANDED: "{player_name}は取り残された。",
}


class PlayerOutcomeObservationFormatter:
    """汎用の既定文へシナリオ宣言の文型を重ねて結果文を作る。"""

    def __init__(
        self,
        templates: Optional[Mapping[PlayerOutcomeEnum, str]] = None,
    ) -> None:
        self._templates = {**_DEFAULT_TEMPLATES, **dict(templates or {})}

    def format(
        self,
        *,
        player_name: str,
        outcome: PlayerOutcomeEnum,
    ) -> Optional[str]:
        """確定結果の観測文を返し、UNRESOLVED なら None を返す。"""
        template = self._templates.get(outcome)
        if template is None:
            return None
        # 文型は ScenarioLoader が書式指定なしの {player_name} だけを許可する。
        # 同じ Python の文型規則で展開し、波括弧の解釈を読込時と一致させる。
        return template.format(player_name=player_name)
