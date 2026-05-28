"""SnsWiringConfig の構造 + __post_init__ assert 挙動。

Issue #227 後続レビュー HIGH-4 Step 8b + HIGH-5: SNS 関連 10 引数を 1 つの
dataclass に集約し、暗黙の配線制約を __post_init__ で実行時 assert する。
"""

import pytest

from ai_rpg_world.application.llm.wiring.wiring_configs import SnsWiringConfig


class TestSnsWiringConfig:
    """SnsWiringConfig の挙動と配線制約。"""

    def test_default_all_fields_none(self) -> None:
        """全 field 省略時は全て None で構築できる (SNS 機能なし状態)。"""
        cfg = SnsWiringConfig()
        assert cfg.post_service is None
        assert cfg.mode_session is None
        assert cfg.page_session is None

    def test_page_session_requires_mode_session(self) -> None:
        """page_session を渡すなら mode_session も必須 (HIGH-5)。"""
        with pytest.raises(ValueError, match="page_session"):
            SnsWiringConfig(page_session=object())

    def test_mode_session_alone_is_allowed(self) -> None:
        """mode_session のみ渡しは許容 (仮想画面なし SNS モード)。"""
        cfg = SnsWiringConfig(mode_session=object())
        assert cfg.mode_session is not None
        assert cfg.page_session is None

    def test_both_session_allowed(self) -> None:
        """mode_session + page_session 両方渡しは正常配線。"""
        m = object()
        p = object()
        cfg = SnsWiringConfig(mode_session=m, page_session=p)
        assert cfg.mode_session is m
        assert cfg.page_session is p
