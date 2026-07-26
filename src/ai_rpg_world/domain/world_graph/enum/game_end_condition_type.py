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
    # 宣言した作業フラグのうち ``min_set_count`` 個以上が立ったら成立。
    #
    # FLAG_SET は 1 個ずつしか見られないので「8 個のうち 6 個」が書けない。
    # 勝ち筋がフラグ 1 個だと **手分けする理由が生まれず**、誰か一人が最短で
    # 目的地へ向かえば終わってしまう。複数の作業を別々の場所に置いて初めて、
    # 散らばる → 襲われる → 誰がどこに居たかが手がかりになる、が回り出す。
    FLAGS_SET_AT_LEAST = "FLAGS_SET_AT_LEAST"
