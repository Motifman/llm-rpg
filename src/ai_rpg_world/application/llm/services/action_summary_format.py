"""行動ログ (直近の出来事) の action_summary を表示用に整形する共有 sanitizer (#552 PR-A)。

# 何のため

``_format_action_summary`` (full orchestrator) と ``runtime_manager`` (escape の失敗 /
wait / listen 等の経路) は raw tool args 全体を ``json.dumps`` して action_summary に
していた。結果 ``object_label`` / ``action_name`` のような outcome args が、
``intention`` / ``expected_result`` / ``emotion_hint`` の主観入力の生 JSON に埋もれて
読みにくかった。

本 sanitizer は raw args から主観入力 4 つを落とし、``inner_thought`` (従来から常時
表示) と outcome args だけを残す。``expected_result`` は chunk_encoding 側で
``[予測: ...]`` として別表記するので、ここで落として二重表示を避ける。

# 注意 (canonical args ではない)

これは **表示用** の整形であり、``ActionResultEntry.action_summary`` に保存はされるが、
loop_guard の引数 fingerprint や tool 実行に使う canonical args とは別物。
fingerprint は ``build_argument_fingerprint`` が raw args から narrative を strip して
計算するので、本整形の有無に依存しない。
"""

from __future__ import annotations

import json
from typing import Any, Mapping, Optional

# action_summary の JSON から落とす主観入力フィールド。
# - expected_result: chunk_encoding が [予測: ...] で別表記するので二重表示回避で隠す
# - intention / emotion_hint: episode の why/felt 側の材料で、recent-events の生 JSON には不要
# - reason: 主に spot_graph_wait の任意理由。wait の result_summary 側に「理由: ...」が
#   残るので action JSON から落としても情報は消えにくい。将来 outcome に効く reason が
#   出たら再検討する (一般名なので注意)。
# inner_thought は従来から常時プロンプトに出ており、外すと挙動が大きく変わるため残す
# (削除するなら別 PR / 別判断)。
ACTION_SUMMARY_HIDDEN_FIELDS = frozenset(
    {"reason", "intention", "expected_result", "emotion_hint"}
)


def format_action_summary_for_display(
    tool_name: str, args: Optional[Mapping[str, Any]] = None
) -> str:
    """tool 名 + (主観ノイズを落とした) args から「直近の出来事」用の行動要約文を作る。

    主観入力 4 フィールドを除いた args を JSON 化する。残る args が無ければ tool 名だけ。
    """
    if not args:
        return f"{tool_name} を実行しました。"
    visible = {k: v for k, v in args.items() if k not in ACTION_SUMMARY_HIDDEN_FIELDS}
    if not visible:
        return f"{tool_name} を実行しました。"
    try:
        args_str = json.dumps(visible, ensure_ascii=False)
    except (TypeError, ValueError):
        args_str = str(visible)
    return f"{tool_name}({args_str}) を実行しました。"


__all__ = ["ACTION_SUMMARY_HIDDEN_FIELDS", "format_action_summary_for_display"]
