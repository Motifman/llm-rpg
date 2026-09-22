"""ItemSpec の payload 往復で、作者が書いた静的定義が落ちないことを固定する。

取引で運ばれるアイテムは `item_spec_to_payload` / `payload_to_item_spec` を
通る。この経路は光源・腐敗・疲労回復を書き出しても読み戻してもいなかったため、
取引を経たアイテムは黙ってただの荷物になっていた。
"""

from __future__ import annotations

from ai_rpg_world.domain.item.enum.item_enum import ItemType, Rarity
from ai_rpg_world.domain.item.value_object.item_spec import ItemSpec
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.item.value_object.max_stack_size import MaxStackSize
from ai_rpg_world.infrastructure.repository.sqlite_item_spec_state_codec import (
    item_spec_to_payload,
    payload_to_item_spec,
)


def _lantern_spec() -> ItemSpec:
    return ItemSpec(
        item_spec_id=ItemSpecId(5001),
        name="往復試験のランタン",
        item_type=ItemType.QUEST,
        rarity=Rarity.COMMON,
        description="暗所を照らし、時間で傷み、使うと疲れが取れる",
        max_stack_size=MaxStackSize(1),
        is_light_source=True,
        spoils_after_ticks=120,
        fatigue_recovery=15,
    )


class TestItemSpecPayloadRoundTrip:
    """item_spec_to_payload と payload_to_item_spec が値を保つ範囲を保証する。"""

    def test_scenario_defined_fields_survive_the_round_trip(self) -> None:
        """光源・腐敗・疲労回復を持つ spec は、payload 往復後も同じ値で戻る。"""
        restored = payload_to_item_spec(item_spec_to_payload(_lantern_spec()))

        assert restored.is_light_source is True
        assert restored.spoils_after_ticks == 120
        assert restored.fatigue_recovery == 15

    def test_payload_without_the_new_keys_decodes_to_defaults(self) -> None:
        """3 つの key を持たない古い payload は、既定の無効値で読める。"""
        payload = item_spec_to_payload(_lantern_spec())
        for key in ("is_light_source", "spoils_after_ticks", "fatigue_recovery"):
            del payload[key]

        restored = payload_to_item_spec(payload)

        assert restored.is_light_source is False
        assert restored.spoils_after_ticks is None
        assert restored.fatigue_recovery == 0
