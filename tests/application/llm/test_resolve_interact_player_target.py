"""interact の ``target_label`` に、物体だけでなく同席プレイヤーも渡せる。

対人 interaction (docs/memory_system/interpersonal_interaction_design.md §3.3)
は専用ツールを増やさず ``interact`` に載せる。対象名の指定作法が物体と人で
揃い、LLM は「行為したいものの名前を書く」だけで済む。

resolver は解決した種別に応じて ``object_id`` か ``target_player_id`` の
どちらかを executor に渡す。両方を同時に埋めない。
"""

from __future__ import annotations

import pytest

from ai_rpg_world.application.llm.contracts.dtos import (
    InventoryToolRuntimeTargetDto,
    PlayerToolRuntimeTargetDto,
    ToolRuntimeContextDto,
    ToolRuntimeTargetDto,
)
from ai_rpg_world.application.llm.services._resolver_helpers import (
    ToolArgumentResolutionException,
)
from ai_rpg_world.application.llm.services._argument_resolvers.spot_graph_resolver import (
    SpotGraphArgumentResolver,
)


def _context(**extra) -> ToolRuntimeContextDto:
    targets = {
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
    }
    targets.update(extra)
    return ToolRuntimeContextDto(targets=targets)


def _resolve(label: str, action: str = "take", context=None):
    return SpotGraphArgumentResolver()._resolve_interact(
        {"target_label": label, "action_name": action, "inner_thought": "…"},
        context if context is not None else _context(),
    )


class TestInteractResolvesPlayerTarget:
    """``target_label`` にプレイヤー名を渡したときの解決結果。"""

    def test_player_display_name_becomes_target_player_id(self) -> None:
        """プレイヤーの表示名を渡すと ``target_player_id`` が埋まる。"""
        out = _resolve("リン")
        assert out["target_player_id"] == 2

    def test_player_target_leaves_object_id_unset(self) -> None:
        """プレイヤーを対象にしたとき ``object_id`` は None のままになる。

        両方が埋まると executor 側が「物体への操作」と「対人操作」の
        どちらなのか判別できなくなる。
        """
        out = _resolve("リン")
        assert out["object_id"] is None

    def test_object_target_leaves_target_player_id_unset(self) -> None:
        """物体を対象にしたとき ``target_player_id`` は None のままになる。"""
        out = _resolve("焚き火跡", action="gather")
        assert out["object_id"] == 10
        assert out["target_player_id"] is None

    def test_short_label_also_resolves_a_player(self) -> None:
        """短縮ラベル (P1) でもプレイヤーとして解決できる。"""
        out = _resolve("P1")
        assert out["target_player_id"] == 2


class TestInteractCrossKindNameCollision:
    """物体とプレイヤーが同じ表示名を持つとき。"""

    def test_ambiguous_name_is_rejected_instead_of_silently_picking_one(self) -> None:
        """同名の物体とプレイヤーがいるとき、黙ってどちらかを選ばず失敗させる。

        表示名の探索は種別を順に見るので、放置すると先に見た種別が常に勝つ。
        「リンを刺したつもりが『リン』という名の物体を調べていた」のような、
        成功として返る誤動作になる。
        """
        context = _context(
            O2=ToolRuntimeTargetDto(
                label="O2",
                kind="spot_graph_object",
                display_name="リン",
                world_object_id=11,
            )
        )
        with pytest.raises(ToolArgumentResolutionException) as e:
            _resolve("リン", context=context)
        assert e.value.error_code == "AMBIGUOUS_TARGET_LABEL"

    def test_short_label_disambiguates_even_when_names_collide(self) -> None:
        """同名でも短縮ラベルで指名すれば一意に決まる。

        曖昧で失敗させる以上、LLM が次に取れる手が要る。
        """
        context = _context(
            O2=ToolRuntimeTargetDto(
                label="O2",
                kind="spot_graph_object",
                display_name="リン",
                world_object_id=11,
            )
        )
        out = _resolve("P1", context=context)
        assert out["target_player_id"] == 2


class TestInteractResolvesHeldItemTarget:
    """所持品欄の道具を interact の第三の対象種別として解決する。"""

    def test_item_name_becomes_item_spec_id(self) -> None:
        """所持道具名は ItemSpecId に解決し、物体・人の ID は空にする。"""
        context = _context(
            I1=InventoryToolRuntimeTargetDto(
                label="I1",
                kind="inventory_item",
                display_name="携帯無線機",
                item_instance_id=31,
                available_interactions=("hail_the_mainland",),
            )
        )

        out = _resolve("携帯無線機", "hail_the_mainland", context)

        assert out["item_spec_id"] == 31
        assert out["object_id"] is None
        assert out["target_player_id"] is None

    @pytest.mark.parametrize("other_kind", ["spot_graph_object", "spot_graph_player"])
    def test_item_name_collision_is_rejected(
        self, other_kind: str
    ) -> None:
        """道具名が物体または人と衝突したら、宣言順で選ばず曖昧として拒否する。"""
        other = ToolRuntimeTargetDto(
            label="X1",
            kind=other_kind,
            display_name="携帯無線機",
            world_object_id=22 if other_kind == "spot_graph_object" else None,
            player_id=2 if other_kind == "spot_graph_player" else None,
        )
        context = _context(
            X1=other,
            I1=InventoryToolRuntimeTargetDto(
                label="I1",
                kind="inventory_item",
                display_name="携帯無線機",
                item_instance_id=31,
            ),
        )

        with pytest.raises(ToolArgumentResolutionException) as error:
            _resolve("携帯無線機", "hail_the_mainland", context)

        assert error.value.error_code == "AMBIGUOUS_TARGET_LABEL"
