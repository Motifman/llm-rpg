"""対人行為の「相手が有効か」を 1 箇所で決める。

負債マップ (docs/precondition_target_state_debt_map.md) の #2。同じ判定が
行動ごとにバラバラに書かれていた。

- ``attack`` はドメインサービスに委譲 (良い)
- ``tend_to_player`` は executor 内にべた書き
- ``give_item`` は転送サービス内に独自実装

負債マップは「give_item に死亡ガードが無い」と書いているが、**確認したら
既に入っていた** (7/25 以降に誰かが直した)。判定が散っていると、直ったことも
壊れたことも一覧では分からない。それ自体がこの括り出しの動機になる。

実 run でも歪みとして出た。死体の同席者行に「背後から襲う」「持ち物を奪う」
「tend_to_player」が並び、追放された人まで同じ行に出続けていた。

判定が散っていると、行動を 1 つ足すたびに「死んだ相手をどう扱うか」を書き
直すことになる。ここに集めて、行動側は **どんな相手が要るか** だけを宣言する。

## 「有効かどうか」は行為によって逆になる

手当ては倒れた相手にしか意味が無く、物を渡すのは立っている相手にしか意味が
無い。真偽値 1 つでは表せないので、要求を ``TargetRequirement`` で宣言する。

## シナリオの前提条件との住み分け

ここに置くのは **どの世界でも成り立つ決まり** だけ (自分自身・別の場所・
退場済み・倒れている)。「役割が keeper のときだけ」のような世界固有の条件は
シナリオの前提条件で書く。engine に世界の設定を持ち込まないため。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional

from ai_rpg_world.domain.player.enum.player_outcome_enum import PlayerOutcomeEnum


class TargetRequirement(Enum):
    """その行為が、相手にどんな状態を要求するか。"""

    #: 立って動ける相手。物を渡す・囁く・襲うなど。
    ACTIVE = "ACTIVE"
    #: 倒れている相手。手当て・持ち物を漁る・死体の報告など。
    INCAPACITATED = "INCAPACITATED"
    #: 同席していれば状態を問わない。見る・話しかけるなど。
    PRESENT = "PRESENT"


@dataclass(frozen=True)
class TargetRejection:
    """対象として使えない理由。

    ``code`` は分析と分岐のため、``message`` は本人に返すため。**両方要る。**
    code だけだとツール結果に出せず、「なぜ駄目か」が本人に届かないので
    同じ手を繰り返す。
    """

    code: str
    message: str


def validate_actionable_target(
    *,
    actor_player_id: int,
    target_player_id: int,
    actor_status: Any,
    target_status: Any,
    target_outcome: PlayerOutcomeEnum,
    same_spot: bool,
    requirement: TargetRequirement,
    target_display_name: str = "相手",
) -> Optional[TargetRejection]:
    """相手が対象として使えるなら ``None``、使えないなら理由を返す。

    判定の順序には意味がある。**より根本的な理由から先に返す。** 「別の場所に
    居る」と「倒れている」が同時に成り立つとき、「倒れている」を返すと相手の
    状態を漏らすことになる (そこに居ないはずの相手の状態を知ることになる)。
    """
    if int(actor_player_id) == int(target_player_id):
        return TargetRejection("TARGET_IS_SELF", "自分自身は対象にできない。")

    # 同席していない相手の状態は、そもそも知り得ない。状態を見る前に弾く。
    if not same_spot:
        return TargetRejection(
            "NOT_IN_SAME_SPOT", f"{target_display_name}はここには居ない。"
        )

    if actor_status is not None and getattr(actor_status, "is_down", False):
        return TargetRejection(
            "ACTOR_IS_DOWN", "自分が倒れているので、何もできない。"
        )

    # 退場が確定した相手は、倒れているかどうかに関わらず対象外。
    #
    # 倒れているかだけを見ると、蘇生の猶予が切れた相手を起こせてしまい
    # **死が確定しなくなる**。
    if target_outcome is not None and target_outcome.is_eliminated:
        return TargetRejection(
            "TARGET_IS_ELIMINATED", f"{target_display_name}はもう息をしていない。"
        )

    target_is_down = bool(getattr(target_status, "is_down", False))

    if requirement is TargetRequirement.ACTIVE and target_is_down:
        return TargetRejection(
            "TARGET_IS_DOWN", f"{target_display_name}は倒れていて応じられない。"
        )
    if requirement is TargetRequirement.INCAPACITATED and not target_is_down:
        return TargetRejection(
            "TARGET_IS_NOT_DOWN", f"{target_display_name}は倒れていない。"
        )
    return None
