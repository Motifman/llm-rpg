"""名前解決ヘルパー。各 formatter で重複実装しない。"""

from typing import Any, Optional, TYPE_CHECKING

from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId

if TYPE_CHECKING:
    pass

FALLBACK_SPOT_LABEL = "不明なスポット"
FALLBACK_PLAYER_LABEL = "不明なプレイヤー"
FALLBACK_ITEM_LABEL = "何かのアイテム"
FALLBACK_NPC_LABEL = "誰か"
FALLBACK_MONSTER_LABEL = "何かのモンスター"
FALLBACK_SKILL_LABEL = "何かのスキル"
FALLBACK_SHOP_LABEL = "どこかのショップ"
FALLBACK_GUILD_LABEL = "どこかのギルド"
FALLBACK_SNS_USER_LABEL = "誰か"


class ObservationNameResolver:
    """スポット・プレイヤー・アイテム等の名前解決を共通化。"""

    def __init__(
        self,
        spot_repository: Optional[Any] = None,
        player_profile_repository: Optional[Any] = None,
        item_spec_repository: Optional[Any] = None,
        item_repository: Optional[Any] = None,
        shop_repository: Optional[Any] = None,
        guild_repository: Optional[Any] = None,
        monster_repository: Optional[Any] = None,
        skill_spec_repository: Optional[Any] = None,
        sns_user_repository: Optional[Any] = None,
    ) -> None:
        self._spot_repository = spot_repository
        self._sns_user_repository = sns_user_repository
        self._player_profile_repository = player_profile_repository
        self._item_spec_repository = item_spec_repository
        self._item_repository = item_repository
        self._shop_repository = shop_repository
        self._guild_repository = guild_repository
        self._monster_repository = monster_repository
        self._skill_spec_repository = skill_spec_repository

    def spot_name(self, spot_id: SpotId) -> str:
        if self._spot_repository:
            spot = self._spot_repository.find_by_id(spot_id)
            if spot:
                return spot.name
        return FALLBACK_SPOT_LABEL

    def player_name(self, player_id: PlayerId) -> str:
        if self._player_profile_repository:
            profile = self._player_profile_repository.find_by_id(player_id)
            if profile and hasattr(profile, "name"):
                return profile.name.value
        return FALLBACK_PLAYER_LABEL

    def item_spec_name(self, item_spec_id_value: int) -> str:
        if self._item_spec_repository is None:
            return FALLBACK_ITEM_LABEL
        try:
            from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
            spec_id = ItemSpecId(item_spec_id_value)
        except Exception:
            return FALLBACK_ITEM_LABEL
        spec = self._item_spec_repository.find_by_id(spec_id)
        if spec is not None:
            return spec.name
        return FALLBACK_ITEM_LABEL

    def item_instance_name(self, item_instance_id: Any) -> str:
        if self._item_repository is None:
            return FALLBACK_ITEM_LABEL
        agg = self._item_repository.find_by_id(item_instance_id)
        if agg is not None:
            return agg.item_spec.name
        return FALLBACK_ITEM_LABEL

    def npc_name(self, npc_id_value: int) -> str:
        if self._monster_repository is None:
            return FALLBACK_NPC_LABEL
        try:
            from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
            npc_object_id = WorldObjectId(npc_id_value)
        except Exception:
            return FALLBACK_NPC_LABEL
        npc = self._monster_repository.find_by_world_object_id(npc_object_id)
        if npc is None:
            return FALLBACK_NPC_LABEL
        return npc.template.name or FALLBACK_NPC_LABEL

    def shop_name(self, shop_id: Any) -> str:
        if self._shop_repository is None:
            return FALLBACK_SHOP_LABEL
        shop = self._shop_repository.find_by_id(shop_id)
        if shop is None:
            return FALLBACK_SHOP_LABEL
        return shop.name.strip() if getattr(shop, "name", "").strip() else FALLBACK_SHOP_LABEL

    def guild_name(self, guild_id: Any) -> str:
        if self._guild_repository is None:
            return FALLBACK_GUILD_LABEL
        guild = self._guild_repository.find_by_id(guild_id)
        if guild is None:
            return FALLBACK_GUILD_LABEL
        return guild.name.strip() if getattr(guild, "name", "").strip() else FALLBACK_GUILD_LABEL

    def monster_name_by_monster_id(self, monster_id: Any) -> str:
        if self._monster_repository is None:
            return FALLBACK_MONSTER_LABEL
        monster = self._monster_repository.find_by_id(monster_id)
        if monster is None:
            return FALLBACK_MONSTER_LABEL
        return monster.template.name or FALLBACK_MONSTER_LABEL

    def skill_name(self, skill_id: Any) -> str:
        if self._skill_spec_repository is None:
            return FALLBACK_SKILL_LABEL
        spec = self._skill_spec_repository.find_by_id(skill_id)
        if spec is None:
            return FALLBACK_SKILL_LABEL
        return spec.name or FALLBACK_SKILL_LABEL

    def sns_user_display_name(self, user_id: Any) -> str:
        """SNS ユーザーの表示名を解決する。"""
        if self._sns_user_repository is None:
            return FALLBACK_SNS_USER_LABEL
        try:
            from ai_rpg_world.domain.sns.value_object.user_id import UserId
            uid = UserId(user_id) if not isinstance(user_id, UserId) else user_id
        except Exception:
            return FALLBACK_SNS_USER_LABEL
        user = self._sns_user_repository.find_by_id(uid)
        if user is None:
            return FALLBACK_SNS_USER_LABEL
        info = user.get_user_profile_info()
        return info.get("display_name", FALLBACK_SNS_USER_LABEL)
