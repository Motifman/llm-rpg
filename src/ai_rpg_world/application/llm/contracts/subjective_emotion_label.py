"""主観エピソード（Episode Encoder）用の感情ラベル。計画書 §4.3 の enum に一致する。"""

from __future__ import annotations

from enum import Enum
from typing import Tuple


class SubjectiveEmotionLabel(str, Enum):
    """LLM 出力・JSON Schema・パース検証はメンバの value（英語小文字）で揃える。"""

    CURIOSITY = "curiosity"
    CAUTION = "caution"
    FEAR = "fear"
    ANXIETY = "anxiety"
    URGENCY = "urgency"
    RELIEF = "relief"
    HOPE = "hope"
    FRUSTRATION = "frustration"
    CONFUSION = "confusion"
    TRUST = "trust"
    DISTRUST = "distrust"
    DETERMINATION = "determination"
    REGRET = "regret"
    SURPRISE = "surprise"
    NEUTRAL = "neutral"


def subjective_emotion_label_values() -> Tuple[str, ...]:
    """定義順（スキーマ・プロンプト列挙用）。"""
    return tuple(m.value for m in SubjectiveEmotionLabel)
