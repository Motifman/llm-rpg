"""raw tool arguments から主観入力 (予測 / 目的 / 感情) を取り出す共有ヘルパ (U2)。

full wiring の ``agent_orchestrator._extract_subjective_text`` をここに移し、
escape (runtime_manager) 経路からも同じ抽出ルールを使えるようにする。full wiring は
いずれ escape に一本化されるため、抽出ロジックは最初から 1 箇所に集約しておく。

抽出ルール: canonical 化前の validated raw arguments から取り、非 str / 空文字は
None に倒す (resolver が subjective fields を落とす場合があるため raw を読む)。
"""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional

# 露出スキーマと一致させる正規キー名 (tool_catalog.subjective_action と対応)。
SUBJECTIVE_ACTION_FIELD_KEYS = ("expected_result", "intention", "emotion_hint")


def extract_subjective_text(arguments: Mapping[str, Any], key: str) -> Optional[str]:
    """raw tool arguments から主観入力フィールドを 1 つ取り出す。

    非文字列・空文字 (空白のみ含む) は None に倒す。
    """
    raw = arguments.get(key)
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    return text or None


def extract_subjective_action_fields(
    arguments: Mapping[str, Any],
) -> Dict[str, Optional[str]]:
    """expected_result / intention / emotion_hint を一括抽出して dict で返す。

    ``do_*`` / recorder にそのまま ``**fields`` で渡せる形。露出 OFF (キー無し)
    の現状では全 None になる。
    """
    return {key: extract_subjective_text(arguments, key) for key in SUBJECTIVE_ACTION_FIELD_KEYS}


__all__ = [
    "SUBJECTIVE_ACTION_FIELD_KEYS",
    "extract_subjective_text",
    "extract_subjective_action_fields",
]
