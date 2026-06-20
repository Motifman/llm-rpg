"""「直近の出来事」の行動行に出す action_summary の整形。

従来は orchestrator / runtime_manager が `f"{tool}({json.dumps(arguments)})"` で
**主観入力を含む全 args を生 JSON で dump** していた。結果に効く args
(target_label / action 等) が inner_thought / intention / expected_result /
emotion_hint に埋もれ、プロンプトのノイズになっていた (#526 後続)。

ここで生成を 1 箇所に寄せ、表示から落とすフィールドを定義する:

- ``inner_thought`` は **残す**。従来から常にプロンプトに出ており、エージェントが
  自分の直前の思考を読む前提で振る舞ってきたため、外すと挙動が大きく変わる。
- ``expected_result`` は ``format_action_result_line_for_recent_events`` 側で
  ``[予測: ...]`` として別表記するため、JSON からは落とす (二重表示の回避)。
- ``intention`` / ``emotion_hint`` / ``reason`` は行動行のノイズなので落とす
  (それぞれ episode.why / episode.felt / 別経路で扱う)。

argument_fingerprint (loop_guard) は別途 raw args から計算され、生 args は trace
ACTION にも残るため、表示整形は監査性を損なわない。
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

# 行動行の JSON から隠すフィールド。inner_thought は残す (常時表示の挙動維持)。
ACTION_SUMMARY_HIDDEN_FIELDS = frozenset(
    {"reason", "intention", "expected_result", "emotion_hint"}
)


def format_action_summary(
    tool_name: str, arguments: Optional[Dict[str, Any]] = None
) -> str:
    """ツール名と引数から「直近の出来事」用の行動要約文を組み立てる。

    ``ACTION_SUMMARY_HIDDEN_FIELDS`` を除いた args だけを JSON 化する。除いた
    結果 args が空になれば ``{tool} を実行しました。`` を返す。
    """
    if not arguments:
        return f"{tool_name} を実行しました。"
    shown = {
        k: v for k, v in arguments.items() if k not in ACTION_SUMMARY_HIDDEN_FIELDS
    }
    if not shown:
        return f"{tool_name} を実行しました。"
    try:
        args_str = json.dumps(shown, ensure_ascii=False)
    except (TypeError, ValueError):
        args_str = str(shown)
    return f"{tool_name}({args_str}) を実行しました。"


__all__ = ["format_action_summary", "ACTION_SUMMARY_HIDDEN_FIELDS"]
