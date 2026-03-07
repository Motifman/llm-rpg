from dataclasses import dataclass
from typing import Optional, Literal
from ai_rpg_world.domain.world.enum.world_enum import DirectionEnum
from ai_rpg_world.domain.player.enum.player_enum import AttentionLevel


@dataclass(frozen=True)
class MoveTileCommand:
    """タイルベースの移動コマンド（人間プレイヤー用）"""
    player_id: int
    direction: DirectionEnum
    
    def __post_init__(self):
        if self.player_id <= 0:
            raise ValueError("player_id must be greater than 0")


@dataclass(frozen=True)
class SetDestinationCommand:
    """目的地設定コマンド（LLMエージェントまたは自動移動用）。座標は不要で、スポットまたはロケーションを指定する。"""
    player_id: int
    destination_type: Literal["spot", "location"]
    target_spot_id: int
    target_location_area_id: Optional[int] = None  # destination_type == "location" のとき必須

    def __post_init__(self):
        if self.player_id <= 0:
            raise ValueError("player_id must be greater than 0")
        if self.target_spot_id <= 0:
            raise ValueError("target_spot_id must be greater than 0")
        if self.destination_type == "location" and (self.target_location_area_id is None or self.target_location_area_id <= 0):
            raise ValueError("target_location_area_id must be positive when destination_type is 'location'")


@dataclass(frozen=True)
class TickMovementCommand:
    """ティックごとの移動実行コマンド"""
    player_id: int

    def __post_init__(self):
        if self.player_id <= 0:
            raise ValueError("player_id must be greater than 0")


@dataclass(frozen=True)
class CancelMovementCommand:
    """経路をキャンセルするコマンド（割り込み時など）。目的地設定を解除し、行動中フラグをクリアする。"""
    player_id: int

    def __post_init__(self):
        if self.player_id <= 0:
            raise ValueError("player_id must be greater than 0")


@dataclass(frozen=True)
class GetSpotInfoCommand:
    """スポット情報取得コマンド"""
    spot_id: int
    
    def __post_init__(self):
        """バリデーション"""
        if self.spot_id <= 0:
            raise ValueError("spot_id must be greater than 0")


@dataclass(frozen=True)
class StoreItemInChestCommand:
    """チェストにアイテムを収納するコマンド"""
    player_id: int
    spot_id: int
    actor_world_object_id: int
    chest_world_object_id: int
    item_instance_id: int

    def __post_init__(self):
        if self.player_id <= 0:
            raise ValueError("player_id must be greater than 0")
        if self.spot_id <= 0:
            raise ValueError("spot_id must be greater than 0")
        if self.actor_world_object_id <= 0:
            raise ValueError("actor_world_object_id must be greater than 0")
        if self.chest_world_object_id <= 0:
            raise ValueError("chest_world_object_id must be greater than 0")
        if self.item_instance_id <= 0:
            raise ValueError("item_instance_id must be greater than 0")


@dataclass(frozen=True)
class TakeItemFromChestCommand:
    """チェストからアイテムを取得するコマンド"""
    player_id: int
    spot_id: int
    actor_world_object_id: int
    chest_world_object_id: int
    item_instance_id: int

    def __post_init__(self):
        if self.player_id <= 0:
            raise ValueError("player_id must be greater than 0")
        if self.spot_id <= 0:
            raise ValueError("spot_id must be greater than 0")
        if self.actor_world_object_id <= 0:
            raise ValueError("actor_world_object_id must be greater than 0")
        if self.chest_world_object_id <= 0:
            raise ValueError("chest_world_object_id must be greater than 0")
        if self.item_instance_id <= 0:
            raise ValueError("item_instance_id must be greater than 0")


@dataclass(frozen=True)
class PlaceObjectCommand:
    """インベントリの指定スロットのアイテムをプレイヤー前方に設置するコマンド"""
    player_id: int
    spot_id: int
    inventory_slot_id: int

    def __post_init__(self):
        if self.player_id <= 0:
            raise ValueError("player_id must be greater than 0")
        if self.spot_id <= 0:
            raise ValueError("spot_id must be greater than 0")
        if self.inventory_slot_id < 0:
            raise ValueError("inventory_slot_id must be non-negative")


@dataclass(frozen=True)
class DestroyPlaceableCommand:
    """プレイヤー前方の設置物を破壊してアイテム化し、インベントリに収納するコマンド"""
    player_id: int
    spot_id: int

    def __post_init__(self):
        if self.player_id <= 0:
            raise ValueError("player_id must be greater than 0")
        if self.spot_id <= 0:
            raise ValueError("spot_id must be greater than 0")


@dataclass(frozen=True)
class ChangeAttentionLevelCommand:
    """プレイヤーの注意レベル（観測フィルタ）を変更するコマンド"""
    player_id: int
    attention_level: AttentionLevel

    def __post_init__(self):
        if self.player_id <= 0:
            raise ValueError("player_id must be greater than 0")
        if not isinstance(self.attention_level, AttentionLevel):
            raise ValueError("attention_level must be an AttentionLevel enum value")


@dataclass(frozen=True)
class InteractWorldObjectCommand:
    """追加引数不要のワールドオブジェクト相互作用コマンド"""

    player_id: int
    target_world_object_id: int

    def __post_init__(self):
        if self.player_id <= 0:
            raise ValueError("player_id must be greater than 0")
        if self.target_world_object_id <= 0:
            raise ValueError("target_world_object_id must be greater than 0")
