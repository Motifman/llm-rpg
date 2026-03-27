"""InMemoryMonsterTemplateRepository - MonsterTemplate のインメモリ実装"""

from typing import Dict, List, Optional

from ai_rpg_world.domain.monster.repository.monster_repository import (
    MonsterTemplateRepository,
    MonsterTemplateWriter,
)
from ai_rpg_world.domain.monster.value_object.monster_template import MonsterTemplate
from ai_rpg_world.domain.monster.value_object.monster_template_id import MonsterTemplateId


class InMemoryMonsterTemplateRepository(MonsterTemplateRepository, MonsterTemplateWriter):
    """MonsterTemplate のインメモリリポジトリ。find_by_name をサポートする。"""

    def __init__(self) -> None:
        self._templates: Dict[MonsterTemplateId, MonsterTemplate] = {}
        self._name_to_template: Dict[str, MonsterTemplate] = {}

    def find_by_id(self, template_id: MonsterTemplateId) -> Optional[MonsterTemplate]:
        """IDでテンプレートを検索"""
        return self._templates.get(template_id)

    def find_by_ids(self, template_ids: List[MonsterTemplateId]) -> List[MonsterTemplate]:
        """IDのリストでテンプレートを検索"""
        return [t for tid in template_ids for t in [self._templates.get(tid)] if t is not None]

    def find_by_name(self, name: str) -> Optional[MonsterTemplate]:
        """名前でテンプレートを検索。同一名は一意に定まる前提。"""
        if not name or not isinstance(name, str):
            return None
        return self._name_to_template.get(name.strip())

    def save(self, template: MonsterTemplate) -> MonsterTemplate:
        """テンプレートを保存"""
        old = self._templates.get(template.template_id)
        if old is not None and old.name != template.name:
            # 名前が変わった場合、旧名前のインデックスを削除
            if old.name in self._name_to_template and self._name_to_template[old.name] == old:
                del self._name_to_template[old.name]
        self._templates[template.template_id] = template
        self._name_to_template[template.name] = template
        return template

    def delete(self, template_id: MonsterTemplateId) -> bool:
        """テンプレートを削除"""
        template = self._templates.get(template_id)
        if template is None:
            return False
        del self._templates[template_id]
        if template.name in self._name_to_template and self._name_to_template[template.name] == template:
            del self._name_to_template[template.name]
        return True

    def find_all(self) -> List[MonsterTemplate]:
        """全てのテンプレートを取得"""
        return list(self._templates.values())

    def replace_template(self, template: MonsterTemplate) -> None:
        self.save(template)

    def delete_template(self, template_id: MonsterTemplateId) -> bool:
        return self.delete(template_id)
