"""resolve_target が object / player を同じ規約で解決することを保証する。

背景: 名前から対象を引く経路が種別ごとに分かれ、**失敗の返し方まで食い違って
いた**。`resolve_object_target` は例外を投げるのに `resolve_player_target` は
`None` を返す (静かに失敗する)。前者は共通ヘルパを使い、後者は同等のループを
手書きしていた。

対人インタラクションでは 1 つの引数に object と player の両方が入るので、
解決を 1 本にまとめ、見つからない / 種別違いを必ず例外で返す。
"""

from __future__ import annotations

import pytest

from ai_rpg_world.application.llm.contracts.dtos import (
    PlayerToolRuntimeTargetDto,
    ToolRuntimeContextDto,
    ToolRuntimeTargetDto,
)
from ai_rpg_world.application.llm.services._resolver_helpers import (
    ToolArgumentResolutionException,
)
from ai_rpg_world.application.llm.services._argument_resolvers.spot_graph_resolver import (
    resolve_target,
)


def _context() -> ToolRuntimeContextDto:
    """object 1 件と player 2 件を持つ runtime context。"""
    return ToolRuntimeContextDto(
        targets={
            "O1": ToolRuntimeTargetDto(
                label="O1",
                kind="spot_graph_object",
                display_name="焚き火跡",
                world_object_id=10,
            ),
            "P1": PlayerToolRuntimeTargetDto(
                label="P1",
                kind="spot_graph_player",
                display_name="リン",
                player_id=2,
            ),
            "P2": PlayerToolRuntimeTargetDto(
                label="P2",
                kind="spot_graph_player",
                display_name="カイト",
                player_id=1,
            ),
        }
    )


class TestResolveTargetAcceptsBothKinds:
    """accept_kinds に複数種別を渡すと、object でも player でも同じ呼び方で解決できる。"""

    def test_object_display_name_resolves(self) -> None:
        """object の表示名を渡すと、その object の target が返る。"""
        target = resolve_target(
            "焚き火跡",
            _context(),
            accept_kinds=("spot_graph_object", "spot_graph_player"),
            label_name="対象の名前",
        )
        assert target.world_object_id == 10

    def test_player_display_name_resolves(self) -> None:
        """player の表示名を渡すと、その player の target が返る。"""
        target = resolve_target(
            "リン",
            _context(),
            accept_kinds=("spot_graph_object", "spot_graph_player"),
            label_name="対象の名前",
        )
        assert target.player_id == 2

    def test_internal_label_key_resolves(self) -> None:
        """内部ラベル (P1 等) を渡しても解決できる (旧形式の後方互換)。"""
        target = resolve_target(
            "P1",
            _context(),
            accept_kinds=("spot_graph_player",),
            label_name="相手の名前",
        )
        assert target.player_id == 2

    def test_concatenated_prompt_line_resolves(self) -> None:
        """"P1 (リン)" のようなプロンプト行の貼り付けも吸収して解決する。"""
        target = resolve_target(
            "P1 (リン)",
            _context(),
            accept_kinds=("spot_graph_player",),
            label_name="相手の名前",
        )
        assert target.player_id == 2


class TestResolveTargetFailsLoudly:
    """解決できない入力は必ず例外になり、None を返す経路が存在しない。"""

    def test_unknown_name_raises_invalid_target_label(self) -> None:
        """候補に無い名前は INVALID_TARGET_LABEL の例外になる。"""
        with pytest.raises(ToolArgumentResolutionException) as exc_info:
            resolve_target(
                "存在しない人",
                _context(),
                accept_kinds=("spot_graph_player",),
                label_name="相手の名前",
            )
        assert exc_info.value.error_code == "INVALID_TARGET_LABEL"

    def test_empty_label_raises_invalid_target_label(self) -> None:
        """空文字は INVALID_TARGET_LABEL の例外になる (静かに None を返さない)。"""
        with pytest.raises(ToolArgumentResolutionException) as exc_info:
            resolve_target(
                "",
                _context(),
                accept_kinds=("spot_graph_player",),
                label_name="相手の名前",
            )
        assert exc_info.value.error_code == "INVALID_TARGET_LABEL"

    def test_display_name_of_other_kind_raises_label_error_with_candidates(
        self,
    ) -> None:
        """別種別の表示名を渡すと INVALID_TARGET_LABEL になり、候補一覧が付く。

        「その名前はプレイヤーです」と正確に言う (INVALID_TARGET_KIND) 方が
        一見親切だが、KIND の文面には候補一覧が付かない。「では何が書けるのか」
        を失う方が LLM にとって痛いので、候補つきの LABEL を返す。
        """
        with pytest.raises(ToolArgumentResolutionException) as exc_info:
            resolve_target(
                "リン",
                _context(),
                accept_kinds=("spot_graph_object",),
                label_name="オブジェクト名",
            )
        assert exc_info.value.error_code == "INVALID_TARGET_LABEL"
        assert "焚き火跡" in str(exc_info.value)

    def test_internal_label_of_other_kind_raises_kind_error(self) -> None:
        """内部ラベルで直接引けたが種別が違うときは INVALID_TARGET_KIND になる。

        表示名検索と違い、内部ラベルの直接一致は「その名前は確かに存在するが
        種類が違う」と断定できるため。
        """
        with pytest.raises(ToolArgumentResolutionException) as exc_info:
            resolve_target(
                "P1",
                _context(),
                accept_kinds=("spot_graph_object",),
                label_name="オブジェクト名",
            )
        assert exc_info.value.error_code == "INVALID_TARGET_KIND"

    def test_unknown_name_message_lists_candidates_of_all_accepted_kinds(self) -> None:
        """候補に無い名前のエラー文には、受け付ける全種別の候補名が並ぶ。

        object だけ / player だけを挙げると「他に何を書けばよいか」が分からず、
        LLM が同じ失敗を繰り返す。
        """
        with pytest.raises(ToolArgumentResolutionException) as exc_info:
            resolve_target(
                "存在しないもの",
                _context(),
                accept_kinds=("spot_graph_object", "spot_graph_player"),
                label_name="対象の名前",
            )
        message = str(exc_info.value)
        assert "焚き火跡" in message
        assert "リン" in message
        assert "カイト" in message
