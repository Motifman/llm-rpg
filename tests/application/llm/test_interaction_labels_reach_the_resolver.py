"""意味ラベルが、表示だけでなく解決の入口まで届くことを保証する。

## 宣言の半分しか届いていなかった

design_decisions #38 は「裸の識別子から意味を推測させたのが `take` 誤読の
原因」と結論し、**選択前の表示**に `display_label` を必須の意味情報として
足した。しかし解決側は直っていない。

    表示:   [麦を刈り取る (reap_wheat), 水をやる (water_field)]
    target: available_interactions=("reap_wheat", "water_field")

同じ 1 つの宣言から作られるのに、**片方だけが意味を落としている**。
action_name を選び直す判断はこの target を入力にするので、意味の無い
識別子の列から意味を読み取れという、#38 が直したはずの状態が残る。

## シナリオではなく builder を見る

保証するのは「あるシナリオの reap_wheat にラベルが在ること」ではない。
シナリオが何を宣言していても、**表示に出た対が解決側にも同じ対で載る**
ことを見る。そのため同梱シナリオは一切読まず、snapshot を直接組む。

ラベルが在ること自体は `parse_interactions.py` が読み込み時に全シナリオへ
強制しているので、ここでは重ねて見ない。
"""

from __future__ import annotations

import pytest

from ai_rpg_world.application.llm.contracts.dtos import ToolRuntimeTargetDto
from ai_rpg_world.application.llm.services.spot_graph_ui_context_builder import (
    SpotGraphUiContextBuilder,
)
from ai_rpg_world.application.world.contracts.dtos import PlayerCurrentStateDto
from ai_rpg_world.application.world_graph.spot_graph_current_state_dtos import (
    SpotGraphInteractionEntry,
    SpotGraphInventoryItemEntry,
    SpotGraphNearbyEntityEntry,
    SpotGraphObjectEntry,
    SpotGraphPlayerSnapshotDto,
)
from ai_rpg_world.domain.player.enum.player_enum import AttentionLevel


def _current_state(snap: SpotGraphPlayerSnapshotDto) -> PlayerCurrentStateDto:
    return PlayerCurrentStateDto(
        player_id=1,
        player_name="アオイ",
        current_spot_id=snap.current_spot_id,
        current_spot_name=snap.current_spot_name,
        current_spot_description=snap.current_spot_description,
        x=None,
        y=None,
        z=None,
        current_player_count=0,
        current_player_ids=set(),
        connected_spot_ids=set(),
        connected_spot_names=set(),
        weather_type="晴れ",
        weather_intensity=0.0,
        current_terrain_type=None,
        visible_objects=[],
        view_distance=0,
        available_moves=None,
        total_available_moves=None,
        attention_level=AttentionLevel.FULL,
        spot_graph_snapshot=snap,
    )


def _build(snap: SpotGraphPlayerSnapshotDto) -> tuple[str, dict]:
    """1 回の build から、表示本文と解決用 target を両方受け取る。

    表示と解決が同じ 1 回の走査から作られることを見たいので、別々に組まない。
    """
    result = SpotGraphUiContextBuilder().build("base", _current_state(snap))
    return result.current_state_text, result.tool_runtime_context.targets


def _only_target_of_kind(targets: dict, kind: str) -> ToolRuntimeTargetDto:
    matched = [t for t in targets.values() if t.kind == kind]
    assert len(matched) == 1, f"{kind} の target が 1 件でない: {len(matched)}"
    return matched[0]


def _wheat_field(
    *interactions: SpotGraphInteractionEntry,
) -> SpotGraphPlayerSnapshotDto:
    return SpotGraphPlayerSnapshotDto(
        current_spot_id=1,
        current_spot_name="麦畑",
        current_spot_description="",
        travel_status_line=None,
        objects=(
            SpotGraphObjectEntry(
                object_id=10,
                name="麦畑",
                description="",
                interactions=interactions,
            ),
        ),
    )


class TestInteractionLabelsReachTheResolver:
    """表示に出た display_label が、同じ操作の対として解決用 target にも載ることを保証する。"""

    def test_public_interaction_label_is_carried_to_the_target(self) -> None:
        """表示に display_label が出た操作は、同じ action_name との対が target の interaction_labels に載る。"""
        snap = _wheat_field(
            SpotGraphInteractionEntry(
                action_name="reap_wheat", display_label="麦を刈り取る"
            ),
            SpotGraphInteractionEntry(
                action_name="water_field", display_label="水をやる"
            ),
        )

        text, targets = _build(snap)

        assert "麦を刈り取る" in text, "前提が崩れている: 表示にラベルが出ていない"
        target = _only_target_of_kind(targets, "spot_graph_object")
        assert dict(target.interaction_labels) == {
            "reap_wheat": "麦を刈り取る",
            "water_field": "水をやる",
        }

    def test_blocked_interaction_label_is_carried_even_when_shown_separately(self) -> None:
        """いま満たしていない操作は表示では別行に回るが、target には他と同じ対で載る。"""
        snap = _wheat_field(
            SpotGraphInteractionEntry(
                action_name="reap_wheat",
                display_label="麦を刈り取る",
                blocking_hints=("まだ実っていない",),
            ),
        )

        text, targets = _build(snap)

        assert "いまできない" in text, "前提が崩れている: 表示が別行に回っていない"
        target = _only_target_of_kind(targets, "spot_graph_object")
        assert dict(target.interaction_labels) == {"reap_wheat": "麦を刈り取る"}
        assert target.available_interactions == ("reap_wheat",)

    def test_hidden_interactions_leave_both_names_and_labels_empty(self) -> None:
        """行為者に操作をすべて伏せた物体は、target の候補もラベルも空のままになる。"""
        snap = SpotGraphPlayerSnapshotDto(
            current_spot_id=1,
            current_spot_name="麦畑",
            current_spot_description="",
            travel_status_line=None,
            objects=(
                SpotGraphObjectEntry(
                    object_id=10,
                    name="納屋の鍵箱",
                    description="",
                    interactions=(),
                    has_actor_hidden_interactions=True,
                ),
            ),
        )

        _, targets = _build(snap)

        target = _only_target_of_kind(targets, "spot_graph_object")
        assert target.available_interactions == ()
        assert target.interaction_labels == ()

    def test_inventory_item_interaction_label_is_carried_to_the_target(self) -> None:
        """所持道具の操作も、表示に出た display_label が target の対として載る。"""
        snap = SpotGraphPlayerSnapshotDto(
            current_spot_id=1,
            current_spot_name="麦畑",
            current_spot_description="",
            travel_status_line=None,
            inventory_items=(
                SpotGraphInventoryItemEntry(
                    item_spec_id=3,
                    item_instance_id=30,
                    slot_id=0,
                    name="鎌",
                    description="",
                    quantity=1,
                    interactions=(
                        SpotGraphInteractionEntry(
                            action_name="sharpen_scythe", display_label="刃を研ぐ"
                        ),
                    ),
                ),
            ),
        )

        _, targets = _build(snap)

        target = _only_target_of_kind(targets, "inventory_item")
        assert dict(target.interaction_labels) == {"sharpen_scythe": "刃を研ぐ"}

    def test_label_for_an_action_that_is_not_offered_is_rejected_at_construction(
        self,
    ) -> None:
        """候補に無い action_name のラベルを渡すと、target の構築時点で ValueError になる。"""
        with pytest.raises(ValueError):
            ToolRuntimeTargetDto(
                label="OBJ1",
                kind="spot_graph_object",
                display_name="納屋の鍵箱",
                available_interactions=("open_lid",),
                interaction_labels=(("count_supplies_pretend", "物資を数える"),),
            )

    @pytest.mark.xfail(
        strict=True,
        reason="#1321 前提: 対人 interaction は表示に出るのに解決側へ候補が渡っていない。運ぶと _pick_action_name の挙動が変わるので別 PR",
    )
    def test_player_interaction_label_is_carried_to_the_target(self) -> None:
        """同席者に対して表示された操作も、target に候補と対で載る。"""
        snap = SpotGraphPlayerSnapshotDto(
            current_spot_id=1,
            current_spot_name="麦畑",
            current_spot_description="",
            travel_status_line=None,
            nearby_entities=(
                SpotGraphNearbyEntityEntry(
                    entity_id=2,
                    name="ハル",
                    entity_type="player",
                    action_entries=(
                        SpotGraphInteractionEntry(
                            action_name="tend_to_player", display_label="介抱して起こす"
                        ),
                    ),
                ),
            ),
        )

        _, targets = _build(snap)

        target = _only_target_of_kind(targets, "spot_graph_player")
        assert dict(target.interaction_labels) == {"tend_to_player": "介抱して起こす"}
