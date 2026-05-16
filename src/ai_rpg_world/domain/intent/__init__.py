"""Intent BC.

LLM ツール呼び出しを「即時 mutate」ではなく「intent を queue に積む」形に
切り替えるための基盤ドメイン。

- ``Intent`` は VO (どのプレイヤーが何を意図したかの不変記述)
- ``IntentQueue`` は集約 (tick 内の intent 群をフェーズ順に保持)
- ``IntentPhase`` で同 tick 内の解決順を決定論的にする

この PR では純追加のみ。実際に既存ツール executor / simulation を書き換える
のは後続 PR (ToolCommandMapper の submit 化 + tick resolve フェーズ追加) で
行う。
"""
