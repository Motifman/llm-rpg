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
    # 「生存」から外れるのは PlayerOutcomeEnum の is_eliminated が真の相手。
    # 倒れている (is_down) だけの相手は蘇生できるので生存として数える
    # (そこで終わらせると蘇生の意味が消える)。
    SURVIVING_PLAYERS_WITH_STATE_AT_MOST = "SURVIVING_PLAYERS_WITH_STATE_AT_MOST"
    # ``required_state`` 側の生存者数が ``comparison_state`` 側以下なら成立。
    # 固定閾値では、片方が追放された後も古い人数で敗北してしまうため、現在の
    # 両陣営をその都度比較する条件を別に持つ。
    SURVIVING_PLAYERS_WITH_STATE_AT_MOST_OTHER_STATE = (
        "SURVIVING_PLAYERS_WITH_STATE_AT_MOST_OTHER_STATE"
    )
    # 宣言した作業フラグのうち ``min_set_count`` 個以上が立ったら成立。
    #
    # FLAG_SET は 1 個ずつしか見られないので「8 個のうち 6 個」が書けない。
    # 勝ち筋がフラグ 1 個だと **手分けする理由が生まれず**、誰か一人が最短で
    # 目的地へ向かえば終わってしまう。複数の作業を別々の場所に置いて初めて、
    # 散らばる → 襲われる → 誰がどこに居たかが手がかりになる、が回り出す。
    FLAGS_SET_AT_LEAST = "FLAGS_SET_AT_LEAST"
    # 個人結果が混在していても、全対象プレイヤーが終局結果へ確定したら
    # 集団 WIN / LOSE を付けずに世界を終了する。
    ALL_PLAYER_OUTCOMES_RESOLVED = "ALL_PLAYER_OUTCOMES_RESOLVED"
