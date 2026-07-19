"""案A (band-gated thinking): 熟考ターンで「必ずツールを 1 つ呼べ」と念押しする指示。

DeepSeek (OpenRouter 経由) は thinking (reasoning) と ``tool_choice="required"`` の
併用を 400 (Thinking mode does not support this tool_choice) で拒否する。そのため
熟考ターンは ``tool_choice="auto"`` にせざるを得ないが、auto だとモデルが行動せず
考察だけ述べて終わる (tool_call なし) ことがある。これを抑えるため、熟考ターンの
プロンプト末尾にだけ「必ずツールを呼べ」と動的に足す。

**なぜ末尾か**: DeepSeek の prefix cache は先頭からの一致長でヒットするので、巨大な
system プロンプト (先頭・安定) を一切変えず末尾に短い指示を足すだけならキャッシュを
壊さない。system を触ると全キャッシュが飛ぶ。熟考ターンは稀なので、末尾の非キャッシュ
分の増加も軽微。通常ターンではこの指示を足さない (プロンプト byte 不変)。
"""

from __future__ import annotations

from typing import Any, Dict, List

FORCE_TOOL_CALL_INSTRUCTION = (
    "重要: 考察だけで終わらせず、必ず提供されたツールのいずれか 1 つを呼び出して"
    "行動を確定してください。文章だけの応答は行動として扱われません。"
)


def append_force_tool_call_instruction(
    messages: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """``messages`` の末尾に強制指示を足した新しいリストを返す (元は変更しない)。

    最後のメッセージ本文が str ならその末尾に追記する (メッセージ数を増やさず
    role 順も乱さない)。空 / 本文が str でない稀なケースでは、末尾に指示メッセージを
    1 件足す。
    """
    if not messages:
        return [{"role": "user", "content": FORCE_TOOL_CALL_INSTRUCTION}]
    new_messages = [dict(m) for m in messages]
    last = new_messages[-1]
    content = last.get("content")
    if isinstance(content, str):
        last["content"] = f"{content.rstrip()}\n\n{FORCE_TOOL_CALL_INSTRUCTION}"
    else:
        new_messages.append(
            {"role": "user", "content": FORCE_TOOL_CALL_INSTRUCTION}
        )
    return new_messages


__all__ = ["FORCE_TOOL_CALL_INSTRUCTION", "append_force_tool_call_instruction"]
