"""直前ターン失敗時に user メッセージ先頭へ差し込む補正ブロック。"""

from __future__ import annotations

from typing import List

from ai_rpg_world.application.llm.contracts.dtos import ActionResultEntry


def build_pre_turn_failure_section(
    newest_first: List[ActionResultEntry],
) -> str:
    """
    get_recent の先頭（最新）が失敗のとき、次の 1 ツール向けの補正セクションを返す。

    newest_first は新しい順（先頭が直前ターン）。2 件目があれば連続同一引数失敗の注意を付与。
    """
    if not newest_first:
        return ""
    latest = newest_first[0]
    if latest.success:
        return ""

    lines: List[str] = [
        "## 前ターンの行動は失敗しました（次の 1 ツールで修正してください）",
        "",
    ]
    code = latest.error_code or "（不明）"
    lines.append(f"- 失敗コード: {code}")
    if latest.tool_name:
        lines.append(f"- 使用したツール: {latest.tool_name}")
    if latest.argument_fingerprint:
        lines.append(f"- 使用した主な引数（正規化）: {latest.argument_fingerprint}")
    lines.append(f"- 結果: {latest.result_summary}")
    if latest.should_reschedule:
        lines.append("- システム上、同条件の再試行がスケジュールされる可能性があります。それでも別のツールや引数を検討してください。")

    if len(newest_first) >= 2:
        prev = newest_first[1]
        if (
            not prev.success
            and latest.tool_name
            and prev.tool_name
            and latest.tool_name == prev.tool_name
            and latest.argument_fingerprint
            and latest.argument_fingerprint == prev.argument_fingerprint
        ):
            lines.extend(
                [
                    "",
                    "### 注意: 同じツール・同じ主な引数での連続失敗",
                    "前ターンに続き同じ組み合わせで失敗しています。表示されている別のラベル・対象・接続先を選ぶか、別種の行動を試してください。",
                ]
            )

    return "\n".join(lines).strip()
