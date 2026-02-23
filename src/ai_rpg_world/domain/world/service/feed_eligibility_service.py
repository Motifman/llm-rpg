"""
餌の適合性判定。
Harvestable がモンスターの嗜好（preferred_feed_item_spec_ids）に合うかどうかを判定する。
リポジトリに依存しない純粋なドメイン関数。
"""

from typing import List, Optional, Set

from ai_rpg_world.domain.item.aggregate.loot_table_aggregate import LootEntry
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId


def is_feed_for_monster(
    loot_table_entries: List[LootEntry],
    preferred_feed_item_spec_ids: Optional[Set[ItemSpecId]],
) -> bool:
    """
    LootTable の entries に、モンスターの嗜好（preferred_feed_item_spec_ids）に
    含まれる item_spec_id が1つでもあれば True。嗜好が None または空の場合は False。
    """
    if not preferred_feed_item_spec_ids:
        return False
    entry_ids = {e.item_spec_id for e in loot_table_entries}
    return bool(entry_ids & preferred_feed_item_spec_ids)
