"""Passive Subjective Recall コンポーザを組み立てる（ルールベース・LLM 不使用）。"""

from __future__ import annotations

import os
from typing import Optional

from ai_rpg_world.application.llm.contracts.interfaces import (
    IPassiveSubjectiveRecallComposer,
    ISubjectiveEpisodeStore,
)
from ai_rpg_world.application.llm.services.passive_subjective_recall_composer import (
    PassiveSubjectiveRecallComposer,
)

_ENV_PASSIVE_SUBJECTIVE_RECALL = "PASSIVE_SUBJECTIVE_RECALL"


def passive_subjective_recall_enabled_from_env() -> bool:
    """未設定時は ON。`0` / `false` / `off` で無効。"""
    raw = (os.environ.get(_ENV_PASSIVE_SUBJECTIVE_RECALL) or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def build_passive_subjective_recall_composer(
    subjective_episode_store: ISubjectiveEpisodeStore,
) -> Optional[IPassiveSubjectiveRecallComposer]:
    """環境変数が ON ならルールベースのコンポーザを返す。無効時は None。"""
    if not passive_subjective_recall_enabled_from_env():
        return None
    return PassiveSubjectiveRecallComposer(
        subjective_episode_store=subjective_episode_store,
    )
