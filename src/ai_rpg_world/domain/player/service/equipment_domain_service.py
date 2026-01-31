from typing import TYPE_CHECKING
from ai_rpg_world.domain.item.enum.item_enum import EquipmentType
from ai_rpg_world.domain.player.enum.equipment_slot_type import EquipmentSlotType
from ai_rpg_world.domain.player.exception.player_exceptions import (
    InvalidEquipmentItemException,
    EquipmentSlotMismatchException
)

if TYPE_CHECKING:
    from ai_rpg_world.domain.item.value_object.item_spec import ItemSpec


class EquipmentDomainService:
    """装備関連のドメインサービス

    装備に関するビジネスルールを表現し、
    リポジトリに依存しない純粋なドメインロジックを提供する。
    """

    # 装備スロットタイプと適合する装備アイテムタイプのマッピング
    EQUIPMENT_SLOT_TO_EQUIPMENT_TYPE_MAPPING: dict[EquipmentSlotType, list[EquipmentType]] = {
        EquipmentSlotType.WEAPON: [EquipmentType.WEAPON],
        EquipmentSlotType.HELMET: [EquipmentType.HELMET],
        EquipmentSlotType.ARMOR: [EquipmentType.ARMOR],
        EquipmentSlotType.SHIELD: [EquipmentType.SHIELD],
        EquipmentSlotType.ACCESSORY: [EquipmentType.ACCESSORY],
        EquipmentSlotType.BOOTS: [EquipmentType.BOOTS],
    }

    @staticmethod
    def validate_equipment_item(item_spec: "ItemSpec") -> None:
        """装備アイテムかどうかを検証

        Args:
            item_spec: 検証対象のアイテムスペック

        Raises:
            InvalidEquipmentItemException: 装備アイテムでない場合
        """
        if not item_spec.is_equipment():
            raise InvalidEquipmentItemException(
                f"Item is not equipment. item_spec_id: {item_spec.item_spec_id.value}, "
                f"item_type: {item_spec.item_type.value}"
            )

    @staticmethod
    def validate_equipment_slot_compatibility(
        item_spec: "ItemSpec",
        target_slot: EquipmentSlotType
    ) -> None:
        """装備スロットの適合性を検証

        Args:
            item_spec: 検証対象のアイテムスペック
            target_slot: 対象の装備スロットタイプ

        Raises:
            EquipmentSlotMismatchException: スロットが適合しない場合
        """
        # まず装備アイテムかどうかを確認
        EquipmentDomainService.validate_equipment_item(item_spec)

        # スロット適合性チェック
        compatible_equipment_types = EquipmentDomainService._get_compatible_equipment_types_for_slot(target_slot)
        if item_spec.equipment_type not in compatible_equipment_types:
            raise EquipmentSlotMismatchException(
                f"Equipment type {item_spec.equipment_type.value} cannot be equipped to "
                f"{target_slot.value} slot. Compatible equipment types: {[t.value for t in compatible_equipment_types]}"
            )

    @staticmethod
    def _get_compatible_equipment_types_for_slot(slot_type: EquipmentSlotType) -> list[EquipmentType]:
        """スロットタイプに対応する適合装備タイプを取得

        Args:
            slot_type: スロットタイプ

        Returns:
            list[EquipmentType]: 適合する装備タイプのリスト
        """
        return EquipmentDomainService.EQUIPMENT_SLOT_TO_EQUIPMENT_TYPE_MAPPING.get(slot_type, [])
