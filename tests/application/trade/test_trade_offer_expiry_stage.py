"""期限切れ取引提案stageが確定区間を必須とする入口契約。"""

from __future__ import annotations

import pytest

from ai_rpg_world.application.trade.services.trade_offer_expiry_stage import (
    TradeOfferExpiryStage,
)


def test_run_rejects_missing_command_scope_before_touching_state() -> None:
    """scope未配線なら期限切れ候補の有無に関係なく即時拒否する。"""
    stage = TradeOfferExpiryStage()

    with pytest.raises(RuntimeError, match="command scope が未配線"):
        stage.run(1)


def test_stage_has_no_legacy_store_freeze_or_observer_dependency() -> None:
    """公開stageは長寿命store・凍結service・直接callbackを保持しない。"""
    stage = TradeOfferExpiryStage()

    assert not hasattr(stage, "_offers")
    assert not hasattr(stage, "_freeze")
    assert not hasattr(stage, "_observer")
