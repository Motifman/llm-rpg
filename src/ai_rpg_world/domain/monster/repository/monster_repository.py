from abc import abstractmethod
from typing import List, Optional
from ai_rpg_world.domain.common.repository import Repository
from ai_rpg_world.domain.monster.aggregate.monster_aggregate import MonsterAggregate
from ai_rpg_world.domain.monster.value_object.monster_id import MonsterId
from ai_rpg_world.domain.monster.value_object.monster_template_id import MonsterTemplateId
from ai_rpg_world.domain.monster.value_object.monster_template import MonsterTemplate
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId


class MonsterRepository(Repository[MonsterAggregate, MonsterId]):
    """モンスター集約のリポジトリインターフェース"""
    @abstractmethod
    def find_by_world_object_id(self, world_object_id: WorldObjectId) -> Optional[MonsterAggregate]:
        """WorldObjectIdに紐づくモンスターを検索"""
        pass


class MonsterTemplateRepository(Repository[MonsterTemplate, MonsterTemplateId]):
    """モンスターテンプレートのリポジトリインターフェース"""
    pass
