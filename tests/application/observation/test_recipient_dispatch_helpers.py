"""配信先解決の共通部品 (`_dispatch.py`) の判定を、具体 strategy から独立に確かめる。

各 strategy を通した検査だけだと、部品自身の分岐 (欠落 / 二重登録 / 理由の空) が
どこまで効くのかが読み取れない。ここで直接固定する。
"""

from __future__ import annotations

import pytest

from ai_rpg_world.application.observation.services.recipient_strategies._dispatch import (
    RecipientRuleWiringError,
    blank_reasons,
    verify_rules_cover_registry,
)


class _StubRegistry:
    """指定した型を担当と答えるだけのレジストリ。"""

    def __init__(self, *event_types: type) -> None:
        self._event_types = event_types

    def get_event_types_for_strategy(self, strategy_key: str) -> tuple:
        return self._event_types


class _EventA:
    """試験用のイベント型。"""


class _EventB:
    """試験用のイベント型 (2 つ目)。"""


def _rule(strategy, event, add) -> None:
    """何もしない配信規則。表に載っていることだけが意味を持つ。"""


class TestMissingRuleIsRejected:
    """担当と登録されたのに配信先が決まらない型を落とす。"""

    def test_event_without_a_rule_or_a_reason_raises(self) -> None:
        """規則にも「配らない」宣言にも無い型があると例外になる。"""
        with pytest.raises(RecipientRuleWiringError) as exc:
            verify_rules_cover_registry(
                registry=_StubRegistry(_EventA, _EventB),
                strategy_key="stub",
                rules={_EventA: _rule},
            )

        assert "_EventB" in str(exc.value)
        assert "_EventA" not in str(exc.value)

    def test_event_declared_as_delivering_to_nobody_is_accepted(self) -> None:
        """「配らない」宣言があれば規則が無くても通る。"""
        verify_rules_cover_registry(
            registry=_StubRegistry(_EventA, _EventB),
            strategy_key="stub",
            rules={_EventA: _rule},
            delivers_to_nobody={_EventB: "試験用。外から見えない内部状態"},
        )

    def test_all_events_covered_by_rules_is_accepted(self) -> None:
        """全型に規則があれば通る (検査が常に落ちる形になっていない)。"""
        verify_rules_cover_registry(
            registry=_StubRegistry(_EventA, _EventB),
            strategy_key="stub",
            rules={_EventA: _rule, _EventB: _rule},
        )


class TestDoubleDeclarationIsRejected:
    """規則と「配らない」宣言の両方に載っている型を落とす。"""

    def test_event_in_both_tables_raises(self) -> None:
        """両方に書くとどちらが意図か読めないので例外になる。"""
        with pytest.raises(RecipientRuleWiringError) as exc:
            verify_rules_cover_registry(
                registry=_StubRegistry(_EventA),
                strategy_key="stub",
                rules={_EventA: _rule},
                delivers_to_nobody={_EventA: "試験用"},
            )

        assert "_EventA" in str(exc.value)


class TestBlankReasonsAreFound:
    """「配らない」理由が書かれていない型を見つける。"""

    def test_empty_reason_is_reported(self) -> None:
        """空文字列の理由は報告される。"""
        assert blank_reasons({_EventA: ""}) == ["_EventA"]

    def test_whitespace_only_reason_is_reported(self) -> None:
        """空白だけの理由も報告される (書いたつもりで中身が無い形)。"""
        assert blank_reasons({_EventA: "   \n  "}) == ["_EventA"]

    def test_written_reason_is_not_reported(self) -> None:
        """理由が書かれていれば報告されない。"""
        assert blank_reasons({_EventA: "外から見えない内部状態なので配らない"}) == []
