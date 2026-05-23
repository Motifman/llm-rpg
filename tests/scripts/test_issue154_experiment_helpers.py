"""issue154 / relay_puzzle 実験スクリプトのヘルパ単体テスト。"""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
_ROOT = _SCRIPTS.parent
for p in (_ROOT, _SCRIPTS):
    s = str(p)
    if s not in sys.path:
        sys.path.insert(0, s)

from issue154_full_tables_experiment import (  # noqa: E402
    _is_a_player,
    _is_b_player,
    _self_third_person_tokens,
)


class TestPlayerMarkers:
    """カイト/リン と旧 A/B ラベルのプレイヤー判定。"""

    def test_kaito_is_a_player(self) -> None:
        """カイトは A 側プレイヤーとして判定される。"""
        assert _is_a_player("カイト") is True
        assert _is_b_player("カイト") is False

    def test_rin_is_b_player(self) -> None:
        """リンは B 側プレイヤーとして判定される。"""
        assert _is_b_player("リン") is True
        assert _is_a_player("リン") is False

    def test_legacy_labels_still_work(self) -> None:
        """旧 A/B ラベルも後方互換で判定される。"""
        assert _is_a_player("A（オペレーター）") is True
        assert _is_b_player("B（侵入者）") is True


class TestSelfThirdPersonTokens:
    """自己三人称検出トークン。"""

    def test_kaito_tokens(self) -> None:
        """カイトの自己参照トークンにカイトさんが含まれる。"""
        assert "カイトさん" in _self_third_person_tokens("カイト")

    def test_rin_tokens(self) -> None:
        """リンの自己参照トークンにリンさんが含まれる。"""
        assert "リンさん" in _self_third_person_tokens("リン")
