"""Intent application layer.

Domain BC ``ai_rpg_world.domain.intent`` の集約・VO をオーケストレーション
するアプリケーションサービス層。

- ``IntentResolutionService``: 既存のツールハンドラを「intent を queue に積み
  → drain → resolve」のフローで実行する
- ``IntentIdGenerator``: tick 内で一意な ID を発行する単純カウンタ
- ``tool_phase_mapping``: ツール名 → ``IntentPhase`` の対応表

この層は wiring から組み立てられ、``ToolCommandMapper`` が opt-in で経由する。
既存の handler シグネチャ ``(player_id: int, args: Mapping) -> LlmCommandResultDto``
には変更を加えないため、tool executor の書き換えは不要。
"""
