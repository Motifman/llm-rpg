"""LLM 関連の非同期スケジューリング抽象。

Issue #470 Phase 1 cleanup A3: ``application/llm/contracts/`` に同居していた
スケジューラ Port を本 package に集約。

スケジューラは **「いつ呼ぶか」の制御抽象** であり、``ports/`` (= 外部 LLM API
への口) とは責務が異なるため別 package に分離した。実装は引き続き
``services/episodic_subjective_completion_schedulers.py`` 等に置く。
"""

from ai_rpg_world.application.llm.scheduler.episodic_subjective_scheduler_port import (
    IEpisodicSubjectiveCompletionScheduler,
)

__all__ = ["IEpisodicSubjectiveCompletionScheduler"]
