"""``spot_graph_tend_to_player`` の resolver が同 spot 制約を message に
明示する (Y_after_pr639_640_200tick 後続、E-36 の観測より)。

Y_after_pr639_640 で観測された失敗:

```
tick=180 pid=4 (カイ, @森の広場)
  action: spot_graph_tend_to_player target_player_label='ノア'
  → error_code=INVALID_TARGET_LABEL
    message='指定された対象ラベルは現在の候補にありません: ノア'
```

このとき ノア (P2) は t=176 に別 spot (深い森) で戦闘不能になっていて
(観測 ``player_downed`` は正しく配信された)、カイの認識は正しい。しかし
tend_to_player の resolver は同 spot 制約により ノアを targets に含めない
ため、単に「候補にない」で弾く。LLM 視点では「名前が間違ってる? #1 付ける?」
と誤解を招く。

**修正**: resolver の失敗 message を tend 固有にし、同 spot 制約を hint する:
「'ノア' は現在の場所にいない、または倒れていない候補です。tend_to_player は
同じ場所で倒れているプレイヤーにだけ使えます。」

executor 側は既に「同 spot だが not down」「同 spot だが actor 自身が down」
「異なる spot」の 3 ケースで良い message を返す実装済み。resolver 側だけを
補強すれば「異 spot なので resolver で弾かれた」ケースの UX が改善する。

error_code は既存 ``INVALID_TARGET_LABEL`` のまま保持 (LLM 学習パスを壊さない、
新 code を導入する必然性は薄い)。**message の中身だけを親切にする**。
"""

from __future__ import annotations

import pytest

from ai_rpg_world.application.llm.contracts.dtos import (
    PlayerToolRuntimeTargetDto,
    ToolRuntimeContextDto,
)
from ai_rpg_world.application.llm.services._argument_resolvers.spot_graph_resolver import (
    SpotGraphArgumentResolver,
)
from ai_rpg_world.application.llm.services._resolver_helpers import (
    ToolArgumentResolutionException,
)
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_SPOT_GRAPH_TEND_TO_PLAYER,
)


def _make_context_with_players(*names: str) -> ToolRuntimeContextDto:
    """指定 name の player を targets に登録した runtime_context を作る。"""
    targets = {}
    for i, name in enumerate(names, start=1):
        label = f"P{i}"
        targets[label] = PlayerToolRuntimeTargetDto(
            label=label,
            kind="spot_graph_player",
            display_name=name,
            player_id=i + 100,
        )
    return ToolRuntimeContextDto(
        current_spot_id=1,
        current_sub_location_id=None,
        targets=targets,
    )


class TestTendToPlayerResolverErrorMessage:
    """resolver 失敗時の message が同 spot 制約を示唆する。"""

    def test_label_が_候補にない場合_同spot制約を_hint_する(self) -> None:
        """P4 カイが遠く離れた spot にいる ノアに tend_to_player を呼ぶ
        シナリオを再現。resolver 側で targets に含まれない (= 別 spot) ため
        失敗するが、message は「候補にない」だけでなく tend の同 spot 制約
        を伝えるべき。"""
        ctx = _make_context_with_players("エイダ", "リオ")
        resolver = SpotGraphArgumentResolver()
        with pytest.raises(ToolArgumentResolutionException) as exc_info:
            resolver.resolve_args(
                TOOL_NAME_SPOT_GRAPH_TEND_TO_PLAYER,
                {"target_player_label": "ノア", "inner_thought": "起こす"},
                ctx,
            )
        msg = str(exc_info.value)
        # 対象名は含まれる
        assert "ノア" in msg, "対象名がエラーに含まれない"
        # 「同じ場所」または「別の場所」または類似の場所制約表現がある
        assert (
            "同じ場所" in msg
            or "同じスポット" in msg
            or "この場所" in msg
        ), (
            f"tend_to_player の同 spot 制約が message で説明されていない: {msg}"
        )
        # 「倒れている」もヒントとして含まれる (target が候補にない場合は
        # spot 違いか未 down かの両方の可能性)
        assert "倒れて" in msg, (
            f"「倒れている」条件が説明されていない: {msg}"
        )

    def test_エラーコードは_INVALID_TARGET_LABEL_を保つ(self) -> None:
        """既存の error_code は変えない (LLM の学習パスと remediation mapping
        を壊さない)。message だけを改善する。"""
        ctx = _make_context_with_players("エイダ")
        resolver = SpotGraphArgumentResolver()
        with pytest.raises(ToolArgumentResolutionException) as exc_info:
            resolver.resolve_args(
                TOOL_NAME_SPOT_GRAPH_TEND_TO_PLAYER,
                {"target_player_label": "ノア", "inner_thought": "起こす"},
                ctx,
            )
        assert exc_info.value.error_code == "INVALID_TARGET_LABEL"

    def test_同spot_に居るplayerが指定された時は_通常通り解決される(self) -> None:
        """同 spot に居る player を渡した場合は既存挙動 (成功) を維持。"""
        ctx = _make_context_with_players("ノア")
        resolver = SpotGraphArgumentResolver()
        result = resolver.resolve_args(
            TOOL_NAME_SPOT_GRAPH_TEND_TO_PLAYER,
            {"target_player_label": "ノア", "inner_thought": "起こす"},
            ctx,
        )
        assert result is not None
        assert result["target_player_id"] == 101
        assert result["target_display_name"] == "ノア"

    def test_空のラベルは_引数欠落として弾かれる(self) -> None:
        """空文字は引数欠落の別 error として扱う (message の内容は既存維持)。"""
        ctx = _make_context_with_players("ノア")
        resolver = SpotGraphArgumentResolver()
        with pytest.raises(ToolArgumentResolutionException) as exc_info:
            resolver.resolve_args(
                TOOL_NAME_SPOT_GRAPH_TEND_TO_PLAYER,
                {"target_player_label": "", "inner_thought": "起こす"},
                ctx,
            )
        assert exc_info.value.error_code == "INVALID_TARGET_LABEL"
