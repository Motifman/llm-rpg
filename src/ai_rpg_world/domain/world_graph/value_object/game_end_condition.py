from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple, Any, Mapping, Optional

from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.enum.game_end_condition_type import GameEndConditionTypeEnum
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    GameEndConditionValidationException,
)


@dataclass(frozen=True)
class GameEndCondition:
    """ゲーム終了条件（脱出ゲーム等）"""

    condition_type: GameEndConditionTypeEnum
    target_spot_id: Optional[SpotId] = None
    target_flag: Optional[str] = None
    tick_limit: Optional[int] = None
    # SURVIVING_PLAYERS_WITH_STATE_AT_MOST 用。数える対象を選ぶ state と、
    # 「これ以下になったら成立」の閾値。
    required_state: Optional[Mapping[str, Any]] = None
    max_surviving: Optional[int] = None
    # FLAGS_SET_AT_LEAST 用。数える対象の作業フラグと、成立に要る個数。
    required_flags: Optional[Tuple[str, ...]] = None
    min_set_count: Optional[int] = None

    def __post_init__(self) -> None:
        """条件型ごとの必須フィールド欠落を構築時に拒否する。"""
        if self.condition_type is GameEndConditionTypeEnum.FLAGS_SET_AT_LEAST:
            flags = tuple(self.required_flags or ())
            if not flags:
                # 空を許すと「0 個中 0 個」で開始した瞬間に勝つ。
                raise GameEndConditionValidationException(
                    "FLAGS_SET_AT_LEAST には required_flags が必要です"
                )
            if len(set(flags)) != len(flags):
                # 重複を数えると 1 個の作業で 2 進む。
                raise GameEndConditionValidationException(
                    f"FLAGS_SET_AT_LEAST の required_flags が重複しています: {flags}"
                )
            if self.min_set_count is None:
                # 既定を「全部」にすると、書き忘れと全部指定が区別できない
                # (SURVIVING_PLAYERS_WITH_STATE_AT_MOST と同じ判断)。
                raise GameEndConditionValidationException(
                    "FLAGS_SET_AT_LEAST には min_set_count が必要です"
                )
            if self.min_set_count <= 0:
                raise GameEndConditionValidationException(
                    "FLAGS_SET_AT_LEAST の min_set_count は 1 以上である必要が"
                    f"あります: {self.min_set_count}"
                )
            if self.min_set_count > len(flags):
                # **絶対に成立しない条件**。書いた本人は勝てるつもりでいるので、
                # run が終わるまで気付けない。
                raise GameEndConditionValidationException(
                    "FLAGS_SET_AT_LEAST の min_set_count が required_flags の数を"
                    f"超えています: {self.min_set_count} > {len(flags)}"
                )
            return

        if self.condition_type == GameEndConditionTypeEnum.FLAG_SET:
            if not isinstance(self.target_flag, str) or not self.target_flag.strip():
                raise GameEndConditionValidationException(
                    "FLAG_SET には target_flag が必要です"
                )
            return
        if self.condition_type == GameEndConditionTypeEnum.TICK_LIMIT:
            if self.tick_limit is None:
                raise GameEndConditionValidationException(
                    "TICK_LIMIT には tick_limit が必要です"
                )
            return
        if (
            self.condition_type
            is GameEndConditionTypeEnum.SURVIVING_PLAYERS_WITH_STATE_AT_MOST
        ):
            if not self.required_state:
                raise GameEndConditionValidationException(
                    "SURVIVING_PLAYERS_WITH_STATE_AT_MOST には required_state が"
                    "必要です (誰を数えるかが決まりません)"
                )
            if self.max_surviving is None:
                # 0 を既定にすると「書き忘れ」と「全滅を指定した」が
                # 区別できなくなる。
                raise GameEndConditionValidationException(
                    "SURVIVING_PLAYERS_WITH_STATE_AT_MOST には max_surviving が"
                    "必要です"
                )
            if int(self.max_surviving) < 0:
                raise GameEndConditionValidationException(
                    "max_surviving は 0 以上である必要があります "
                    f"(負の閾値は成立しえません): {self.max_surviving}"
                )
            return
        if self.condition_type in (
            GameEndConditionTypeEnum.ALL_AT_SPOT,
            GameEndConditionTypeEnum.ANY_AT_SPOT,
        ):
            if self.target_spot_id is None:
                raise GameEndConditionValidationException(
                    f"{self.condition_type.value} には target_spot_id が必要です"
                )
            return
        if self.condition_type is GameEndConditionTypeEnum.ALL_PLAYER_OUTCOMES_RESOLVED:
            # 全対象プレイヤーが終局結果へ確定したかだけを見る条件で、どこで・
            # 何を数えるかを条件側に書かない。指定する値が無いので必須も無い。
            return
        # ここまでで return しなかった条件型は、分岐を書き忘れたものだけ。
        #
        # 以前は最後の分岐を素通りして終わっていた。すると **新しい条件型は
        # 検証なしで構築でき**、必須フィールドが空のまま run に入る。#848 で
        # 条件型を足したときに検査が漏れたのと同じ形が、生成側にも残っていた。
        #
        # 落とす側に倒すのは passage.py / attacker_ref.py と同じ判断。
        raise GameEndConditionValidationException(
            f"未知の終了条件型です: {self.condition_type.value} / "
            "GameEndCondition.__post_init__ に必須フィールドの検証を追加して"
            "ください"
        )
