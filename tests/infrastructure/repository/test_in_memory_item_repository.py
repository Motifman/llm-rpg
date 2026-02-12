import pytest
from ai_rpg_world.domain.item.aggregate.item_aggregate import ItemAggregate
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
from ai_rpg_world.domain.item.value_object.item_spec import ItemSpec
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.item.value_object.max_stack_size import MaxStackSize
from ai_rpg_world.domain.item.enum.item_enum import ItemType, Rarity
from ai_rpg_world.infrastructure.repository.in_memory_item_repository import InMemoryItemRepository
from ai_rpg_world.infrastructure.repository.in_memory_data_store import InMemoryDataStore
from ai_rpg_world.infrastructure.unit_of_work.in_memory_unit_of_work import InMemoryUnitOfWork


class TestInMemoryItemRepository:
    @pytest.fixture
    def setup(self):
        data_store = InMemoryDataStore()
        data_store.clear_all()
        def create_uow():
            return InMemoryUnitOfWork(unit_of_work_factory=create_uow, data_store=data_store)
        uow, _ = InMemoryUnitOfWork.create_with_event_publisher(unit_of_work_factory=create_uow, data_store=data_store)
        repo = InMemoryItemRepository(data_store, uow)
        return repo, data_store, uow

    def _create_item(self, spec_id: int, name: str, item_type: ItemType = ItemType.MATERIAL) -> ItemSpec:
        return ItemSpec(
            item_spec_id=ItemSpecId(spec_id),
            name=name,
            item_type=item_type,
            rarity=Rarity.COMMON,
            description="test description",
            max_stack_size=MaxStackSize(64)
        )

    def test_save_and_find_by_id(self, setup):
        repo, _, _ = setup
        spec = self._create_item(1, "Test Item")
        instance_id = repo.generate_item_instance_id()
        item = ItemAggregate.create(instance_id, spec, quantity=10)
        
        repo.save(item)
        found = repo.find_by_id(instance_id)
        
        assert found is not None
        assert found.item_instance_id == instance_id
        assert found.quantity == 10
        assert found.item_spec.name == "Test Item"

    def test_find_by_spec_id(self, setup):
        repo, _, _ = setup
        spec1 = self._create_item(1, "Item 1")
        spec2 = self._create_item(2, "Item 2")
        
        item1 = ItemAggregate.create(repo.generate_item_instance_id(), spec1)
        item2 = ItemAggregate.create(repo.generate_item_instance_id(), spec1)
        item3 = ItemAggregate.create(repo.generate_item_instance_id(), spec2)
        
        repo.save(item1)
        repo.save(item2)
        repo.save(item3)
        
        results = repo.find_by_spec_id(ItemSpecId(1))
        assert len(results) == 2
        assert all(r.item_spec.item_spec_id == ItemSpecId(1) for r in results)

    def test_delete(self, setup):
        repo, _, _ = setup
        item = ItemAggregate.create(repo.generate_item_instance_id(), self._create_item(1, "Item"))
        repo.save(item)
        
        assert repo.find_by_id(item.item_instance_id) is not None
        
        repo.delete(item.item_instance_id)
        assert repo.find_by_id(item.item_instance_id) is None
