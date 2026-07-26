from enum import Enum


class GameEndConditionTypeEnum(str, Enum):
    """脱出・シナリオ用のゲーム終了条件の種類"""

    ALL_AT_SPOT = "ALL_AT_SPOT"
    ANY_AT_SPOT = "ANY_AT_SPOT"
    FLAG_SET = "FLAG_SET"
    TICK_LIMIT = "TICK_LIMIT"
    # 陣営の全滅。``required_state`` を満たす **生存** プレイヤーが
    # ``max_surviving`` 人以下なら成立する。
    #
    # 「生存」から外れるのは PlayerOutcomeEnum.DEAD が確定した相手だけ。
    # 倒れている (is_down) だけの相手は蘇生できるので生存として数える
    # (そこで終わらせると蘇生の意味が消える)。
    SURVIVING_PLAYERS_WITH_STATE_AT_MOST = "SURVIVING_PLAYERS_WITH_STATE_AT_MOST"
