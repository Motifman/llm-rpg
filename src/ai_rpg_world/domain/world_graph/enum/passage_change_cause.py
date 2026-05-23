"""``ConnectionStateChangedEvent`` の発生原因を分類する enum。

Issue #180: passage state 変化を観測する側 (LLM agent / NPC) が「これは
相手の能動的行動か、自動制御か」を区別できるよう、event に原因メタデータを
持たせる。formatter は cause を見て「ガチャッと閉まった」(actor action) /
「ひとりでに閉まった」(reactive) のように prose を分岐する。

cause は **誰が** ではなく **何の仕組みが** トリガしたかを表す:

- ``ACTOR_ACTION``: tool 経由の interaction effect / 明示的なツール呼び出し
  (操作盤を切った、レバーを引いた、ドアを叩き割った 等)
- ``REACTIVE``: ``ReactivePassageBindingStageService`` 由来 (条件式の自動
  評価による状態切替。例: 制御室から人が居なくなって電源が落ちる)
- ``SCENARIO_EVENT``: ``SpotGraphScenarioEventStageService`` 由来 (タイマや
  scenario_events の effect で発火)
- ``SYNCHRONIZED_ACTION``: ``SynchronizedActionResolverStageService`` 由来
  (協力ギミック #13 の同期完了 resolve による変更)
- ``UNKNOWN``: 既定値。後方互換 (cause を指定しない既存呼び出し) のために存在
"""

from __future__ import annotations

from enum import Enum


class PassageChangeCauseEnum(str, Enum):
    """passage state 変化の原因カテゴリ。"""

    ACTOR_ACTION = "ACTOR_ACTION"
    REACTIVE = "REACTIVE"
    SCENARIO_EVENT = "SCENARIO_EVENT"
    SYNCHRONIZED_ACTION = "SYNCHRONIZED_ACTION"
    UNKNOWN = "UNKNOWN"
