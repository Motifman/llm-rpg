"""
JobシステムからSpotActionシステムへの移行テスト

移行アダプター層の動作とデータ保持を検証
"""

import pytest
from src.models.agent import Agent
from src.models.job import JobAgent, JobType, CraftsmanAgent, MerchantAgent, ServiceProviderAgent, TraderAgent, ProducerAgent, AdventurerAgent
from src.models.spot_action import Role, Permission
from src.models.job_migration import JobToRoleMapper, JobAgentAdapter, WorldJobMigrationHelper
from src.models.item import Item
from src.systems.world import World


def test_job_to_role_mapper():
    """JobToRoleMapperの基本マッピングテスト"""
    
    # 基本JobType -> Role マッピング
    craftsman = JobAgent("test_craftsman", "テスト職人", JobType.CRAFTSMAN)
    assert JobToRoleMapper.map_job_agent_to_role(craftsman) == Role.CRAFTSMAN
    
    merchant = JobAgent("test_merchant", "テスト商人", JobType.MERCHANT)
    assert JobToRoleMapper.map_job_agent_to_role(merchant) == Role.MERCHANT
    
    adventurer = JobAgent("test_adventurer", "テスト冒険者", JobType.ADVENTURER)
    assert JobToRoleMapper.map_job_agent_to_role(adventurer) == Role.ADVENTURER
    
    producer = JobAgent("test_producer", "テスト生産者", JobType.PRODUCER)
    assert JobToRoleMapper.map_job_agent_to_role(producer) == Role.FARMER


def test_detailed_job_mapping():
    """詳細な職業特化マッピングのテスト"""
    
    # CraftsmanAgent specialty mapping
    blacksmith = CraftsmanAgent("blacksmith1", "鍛冶師", "blacksmith")
    assert JobToRoleMapper.map_job_agent_to_role(blacksmith) == Role.BLACKSMITH
    
    alchemist = CraftsmanAgent("alchemist1", "錬金術師", "alchemist")
    assert JobToRoleMapper.map_job_agent_to_role(alchemist) == Role.ALCHEMIST
    
    # MerchantAgent business_type mapping
    innkeeper_merchant = MerchantAgent("innkeeper1", "宿屋主人", "innkeeper")
    assert JobToRoleMapper.map_job_agent_to_role(innkeeper_merchant) == Role.INNKEEPER
    
    # ServiceProviderAgent service_type mapping
    dancer = ServiceProviderAgent("dancer1", "踊り子", "dancer")
    assert JobToRoleMapper.map_job_agent_to_role(dancer) == Role.DANCER
    
    priest = ServiceProviderAgent("priest1", "神官", "priest")
    assert JobToRoleMapper.map_job_agent_to_role(priest) == Role.PRIEST
    
    # ProducerAgent production_type mapping
    farmer = ProducerAgent("farmer1", "農家", "farmer")
    assert JobToRoleMapper.map_job_agent_to_role(farmer) == Role.FARMER
    
    miner = ProducerAgent("miner1", "鉱夫", "miner")
    assert JobToRoleMapper.map_job_agent_to_role(miner) == Role.MINER


def test_permission_mapping():
    """Role -> Permission マッピングのテスト"""
    assert JobToRoleMapper.get_default_permission_for_role(Role.SHOP_KEEPER) == Permission.OWNER
    assert JobToRoleMapper.get_default_permission_for_role(Role.INNKEEPER) == Permission.OWNER
    assert JobToRoleMapper.get_default_permission_for_role(Role.BLACKSMITH) == Permission.EMPLOYEE
    assert JobToRoleMapper.get_default_permission_for_role(Role.ALCHEMIST) == Permission.EMPLOYEE
    assert JobToRoleMapper.get_default_permission_for_role(Role.ADVENTURER) == Permission.CUSTOMER
    assert JobToRoleMapper.get_default_permission_for_role(Role.MERCHANT) == Permission.CUSTOMER


def test_job_agent_adapter():
    """JobAgentAdapterのテスト"""
    
    # CraftsmanAgentの移行テスト
    old_alchemist = CraftsmanAgent("alchemist1", "錬金術師ルナ", "alchemist")
    old_alchemist.add_money(150)
    old_alchemist.current_hp = 80
    old_alchemist.current_mp = 45
    
    # アイテムを追加
    herb = Item("herb", "薬草")
    old_alchemist.add_item(herb)
    
    adapter = JobAgentAdapter(old_alchemist)
    new_agent = adapter.get_adapted_agent()
    
    # 基本データの移行確認
    assert new_agent.agent_id == "alchemist1"
    assert new_agent.name == "錬金術師ルナ"
    assert new_agent.get_role() == Role.ALCHEMIST
    assert new_agent.get_money() == 150
    assert new_agent.current_hp == 80
    assert new_agent.current_mp == 45
    assert new_agent.get_item_count("herb") == 1
    
    # アダプター機能の確認
    assert adapter.get_role() == Role.ALCHEMIST
    assert adapter.get_default_permission() == Permission.EMPLOYEE
    
    # Job固有情報の取得
    summary = adapter.get_job_skills_summary()
    assert summary["specialty"] == "alchemist"
    assert summary["mapped_role"] == "alchemist"
    assert "enhancement_success_rate" in summary


def test_merchant_agent_adapter():
    """MerchantAgentの移行テスト"""
    old_innkeeper = MerchantAgent("innkeeper1", "宿屋の主人", "innkeeper")
    old_innkeeper.add_money(300)
    
    adapter = JobAgentAdapter(old_innkeeper)
    new_agent = adapter.get_adapted_agent()
    
    assert new_agent.get_role() == Role.INNKEEPER
    assert adapter.get_default_permission() == Permission.OWNER
    
    summary = adapter.get_job_skills_summary()
    assert summary["business_type"] == "innkeeper"
    assert summary["mapped_role"] == "innkeeper"


def test_world_migration_helper():
    """WorldJobMigrationHelperのテスト"""
    world = World()
    migration_helper = WorldJobMigrationHelper(world)
    
    # JobAgentをワールドに追加
    craftsman = CraftsmanAgent("craftsman1", "職人", "blacksmith")
    craftsman.add_money(200)
    world.add_agent(craftsman)
    
    merchant = MerchantAgent("merchant1", "商人", "trader")
    merchant.add_money(150)
    world.add_agent(merchant)
    
    # 通常のAgentも追加（移行対象外）
    normal_agent = Agent("normal1", "一般人", Role.CITIZEN)
    world.add_agent(normal_agent)
    
    # 移行前の状態確認
    summary = migration_helper.get_migration_summary()
    assert summary["total_agents"] == 3
    assert summary["job_agents"] == 2
    assert summary["role_agents"] == 1
    
    # 全JobAgentを移行
    migrated_agents = migration_helper.migrate_all_job_agents()
    
    # 移行後の状態確認
    assert len(migrated_agents) == 2
    assert "craftsman1" in migrated_agents
    assert "merchant1" in migrated_agents
    
    # ワールド内のエージェントが移行されているか確認
    new_craftsman = world.get_agent("craftsman1")
    assert isinstance(new_craftsman, Agent)
    assert new_craftsman.get_role() == Role.BLACKSMITH
    assert new_craftsman.get_money() == 200
    
    new_merchant = world.get_agent("merchant1")
    assert isinstance(new_merchant, Agent)
    assert new_merchant.get_role() == Role.TRADER  # "trader" business_type → TRADER Role
    assert new_merchant.get_money() == 250  # 150 + 100 (MERCHANT初期ボーナス)
    
    # 通常のAgentは変更されていないはず
    unchanged_agent = world.get_agent("normal1")
    assert unchanged_agent is normal_agent
    
    # 移行後のサマリー確認
    final_summary = migration_helper.get_migration_summary()
    assert final_summary["job_agents"] == 0
    assert final_summary["role_agents"] == 3


def test_individual_agent_migration():
    """個別エージェント移行のテスト"""
    world = World()
    migration_helper = WorldJobMigrationHelper(world)
    
    # ServiceProviderAgentを追加
    dancer = ServiceProviderAgent("dancer1", "踊り子", "dancer")
    dancer.add_money(100)
    world.add_agent(dancer)
    
    # 個別移行実行
    new_dancer = migration_helper.migrate_agent_to_role_system("dancer1")
    
    assert new_dancer is not None
    assert new_dancer.get_role() == Role.DANCER
    assert new_dancer.get_money() == 200  # 100 + 100 (ServiceProviderAgentはMERCHANTタイプなので初期ボーナス)
    
    # ワールド内のエージェントが置換されているか確認
    world_dancer = world.get_agent("dancer1")
    assert world_dancer is new_dancer


def test_adapter_job_skills_summary():
    """各種JobAgentのスキルサマリーテスト"""
    
    # TraderAgentのテスト
    trader = TraderAgent("trader1", "商人", "weapons")
    trader.add_money(250)
    
    adapter = JobAgentAdapter(trader)
    summary = adapter.get_job_skills_summary()
    
    assert summary["trade_specialty"] == "weapons"
    assert summary["mapped_role"] == "merchant"
    assert "negotiation_skill" in summary
    assert "inventory_items" in summary
    
    # ProducerAgentのテスト
    woodcutter = ProducerAgent("woodcutter1", "木こり", "woodcutter")
    
    adapter = JobAgentAdapter(woodcutter)
    summary = adapter.get_job_skills_summary()
    
    assert summary["production_type"] == "woodcutter"
    assert summary["mapped_role"] == "woodcutter"
    assert "production_efficiency" in summary
    assert "gathering_tools" in summary


if __name__ == "__main__":
    # 基本テストを実行
    print("🧪 Job移行システムのテスト開始")
    
    test_job_to_role_mapper()
    print("✅ JobToRoleMapperテスト完了")
    
    test_detailed_job_mapping()
    print("✅ 詳細マッピングテスト完了")
    
    test_permission_mapping()
    print("✅ 権限マッピングテスト完了")
    
    test_job_agent_adapter()
    print("✅ JobAgentAdapterテスト完了")
    
    test_merchant_agent_adapter()
    print("✅ MerchantAgentAdapterテスト完了")
    
    test_world_migration_helper()
    print("✅ WorldMigrationHelperテスト完了")
    
    test_individual_agent_migration()
    print("✅ 個別移行テスト完了")
    
    test_adapter_job_skills_summary()
    print("✅ スキルサマリーテスト完了")
    
    print("🎉 すべてのテストが完了しました！") 