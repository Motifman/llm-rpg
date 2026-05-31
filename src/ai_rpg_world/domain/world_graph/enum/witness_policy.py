"""Witness ポリシー: 行為がどの範囲のプレイヤーに観測されるか (Phase C)。

これまで spot-graph 系の event (drop / pickup / give / interact 等) はすべて
「同スポット内の他プレイヤーには配信される」一律ルールだった。隠匿行動
(裏切り / こっそり盗む / 秘密の探索) を成立させるには、行為ごとに
「誰の目に入るか」を選べる必要がある。

本 enum は v2 design §7 の Phase C で挙げた次の 3 段階のうち、最初の 2 つを
表現する:

- SAME_SPOT: 同じスポットに居る他プレイヤーには観測される (デフォルト、
  これまでの振る舞い)
- ACTOR_ONLY: 行為者本人にしか観測されない (recipient strategy が空集合を
  返す)。「こっそり drop」「こっそり pickup」「ステルス探索」。

将来の EXPLICIT_TARGETS (特定の player に対してのみ観測) は別途追加する想定
だが、設計の複雑さが上がるので本 PR では含めない。

設計判断:
- domain enum として置く理由: event の field として参照されるので、event を
  発火する複数のサービス / handler が値を共有する必要がある。infrastructure
  や application 層ではなく domain 値オブジェクトに置く方が層の整合が取れる
- "STEALTH" ではなく "ACTOR_ONLY" を採用: 観測経路の仕様を直接表す名前にし、
  ニュアンス (こそこそした / 秘密の) を込めない。LLM tool 側は "stealth: bool"
  のような UI を被せる
"""

from enum import Enum


class WitnessPolicy(Enum):
    """行為の観測範囲。"""

    # 同スポット内の他プレイヤーに観測される (これまでのデフォルト)。
    SAME_SPOT = "SAME_SPOT"

    # 行為者本人にしか観測が届かない。recipient strategy が空集合を返す。
    # 「こっそり盗む」「こっそり置く」を表現するときに使う。
    ACTOR_ONLY = "ACTOR_ONLY"
