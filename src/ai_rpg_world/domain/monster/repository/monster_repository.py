from abc import abstractmethod
from typing import List, Optional
from ai_rpg_world.domain.common.repository import Repository
from ai_rpg_world.domain.monster.aggregate.monster_aggregate import MonsterAggregate
from ai_rpg_world.domain.monster.value_object.monster_id import MonsterId
from ai_rpg_world.domain.monster.value_object.monster_template_id import MonsterTemplateId
from ai_rpg_world.domain.monster.value_object.monster_template import MonsterTemplate


class MonsterRepository(Repository[MonsterAggregate, MonsterId]):
    """モンスター集約のリポジトリインターフェース"""
    pass


class MonsterTemplateRepository(Repository[MonsterTemplate, MonsterTemplateId]):
    """モンスターテンプレートのリポジトリインターフェース"""
    pass
