import pytest
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.item.value_object.item_spec import ItemSpec
from ai_rpg_world.domain.item.value_object.max_stack_size import MaxStackSize
from ai_rpg_world.domain.item.enum.item_enum import ItemType, Rarity, EquipmentType
from ai_rpg_world.infrastructure.repository.in_memory_item_spec_repository import InMemoryItemSpecRepository


class TestInMemoryItemSpecRepository:
    @pytest.fixture
    def repo(self):
        return InMemoryItemSpecRepository()

    def test_find_by_id_returns_vo(self, repo):
        # Sample data contains ID 1 (鉄の剣)
        spec = repo.find_by_id(ItemSpecId(1))
        assert spec is not None
        # Should be an ItemSpec or ItemSpecReadModel that works as ItemSpec
        assert spec.name == "鉄の剣"
        assert isinstance(spec.item_spec_id, ItemSpecId)

    def test_find_by_name(self, repo):
        spec = repo.find_by_name("鉄の剣")
        assert spec is not None
        assert spec.item_spec_id == ItemSpecId(1)

    def test_find_by_type(self, repo):
        specs = repo.find_by_type(ItemType.EQUIPMENT)
        assert len(specs) > 0
        assert all(s.item_type == ItemType.EQUIPMENT for s in specs)
