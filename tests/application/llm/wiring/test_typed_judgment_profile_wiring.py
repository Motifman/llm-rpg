"""型付き判断を profile から入れられることを、次の PR で満たす。

ポートとアダプタは在るが、**profile から有効化する経路がまだ無い**。この
状態を xfail-strict で残す (design_decisions #12)。配線した瞬間に
"expected fail but passed" で落ちるので、mark を外す作業が強制される。

コメントで「後で配線する」と書くと恒久放置される。PR #439 の setter が
PR #444 まで 1 ヶ月放置されたのと同じ形になる。
"""

from __future__ import annotations

import pytest

from ai_rpg_world.application.llm.wiring.resolved_runtime_config import (
    ResolvedLlmRuntimeConfig,
)


@pytest.mark.xfail(
    strict=True,
    reason="#1319: ポートとアダプタは在るが profile 経路が未配線 (次の PR で配線)",
)
def test_a_profile_can_turn_typed_judgment_on() -> None:
    """profile に TYPED_JUDGMENT_PROVIDER を書くと、解決済み設定に載る。"""
    config = ResolvedLlmRuntimeConfig.from_mapping(
        values={"TYPED_JUDGMENT_PROVIDER": "jev"}
    )

    assert config.typed_judgment_provider == "jev"
