"""
モンスタースキル使用に関するアプリケーション例外定義
"""

from ai_rpg_world.application.common.exceptions import ApplicationException


class MonsterNotFoundForSkillException(ApplicationException):
    """スキル使用時にモンスターが見つからない場合の例外"""

    def __init__(self, world_object_id: int):
        message = f"モンスターが見つかりません: WorldObjectId={world_object_id}"
        super().__init__(message, world_object_id=world_object_id)


class MonsterSkillNotFoundInSlotException(ApplicationException):
    """指定スロットにスキルが装備されていない場合の例外"""

    def __init__(self, monster_id: int, slot_index: int):
        message = f"モンスター {monster_id} のスロット {slot_index} にスキルが装備されていません"
        super().__init__(message, monster_id=monster_id, slot_index=slot_index)


class MapNotFoundForMonsterSkillException(ApplicationException):
    """スキル使用時にマップが見つからない場合の例外"""

    def __init__(self, spot_id: int):
        message = f"マップが見つかりません: SpotId={spot_id}"
        super().__init__(message, spot_id=spot_id)


class MonsterNotOnMapException(ApplicationException):
    """モンスターは存在するがマップ上にオブジェクトが存在しない場合の例外（データ整合性エラー）"""

    def __init__(self, world_object_id: int, spot_id: int):
        message = (
            f"モンスターのワールドオブジェクトがマップ上に存在しません: "
            f"WorldObjectId={world_object_id}, SpotId={spot_id}"
        )
        super().__init__(message, world_object_id=world_object_id, spot_id=spot_id)


class MonsterNotFoundException(ApplicationException):
    """スポーン時にモンスターが見つからない場合の例外"""

    def __init__(self, monster_id: int):
        message = f"モンスターが見つかりません: MonsterId={monster_id}"
        super().__init__(message, monster_id=monster_id)


class MonsterAlreadySpawnedApplicationException(ApplicationException):
    """スポーン時に既に出現済みの場合の例外"""

    def __init__(self, monster_id: int):
        message = f"モンスターは既に出現済みです: MonsterId={monster_id}"
        super().__init__(message, monster_id=monster_id)
