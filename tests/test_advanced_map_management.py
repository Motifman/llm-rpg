#!/usr/bin/env python3
"""
高度なマップ管理機能のテスト
"""

import pytest
import tempfile
import json
import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from game.world.spot_manager import SpotManager
from game.world.spot_group import SpotGroup, SpotGroupConfig
from game.world.entrance_manager import EntranceManager, EntranceConfig
from game.world.map_builder import MapBuilder
from game.world.spot import Spot


class TestSpotGroup:
    """SpotGroupのテスト"""
    
    def test_spot_group_creation(self):
        """SpotGroupの作成テスト"""
        config = SpotGroupConfig(
            group_id="test_group",
            name="テストグループ",
            description="テスト用のグループ",
            spot_ids=["spot1", "spot2"],
            entrance_spot_ids=["spot1"],
            tags=["test", "demo"]
        )
        
        group = SpotGroup(config)
        assert group.config.group_id == "test_group"
        assert group.config.name == "テストグループ"
        assert len(group.spots) == 0
        assert len(group.tags) == 2
        assert "test" in group.tags
        assert "demo" in group.tags
    
    def test_spot_group_add_spot(self):
        """SpotGroupへのスポット追加テスト"""
        config = SpotGroupConfig(
            group_id="test_group",
            name="テストグループ",
            description="テスト用のグループ",
            spot_ids=["spot1", "spot2"],
            entrance_spot_ids=["spot1"]
        )
        
        group = SpotGroup(config)
        spot1 = Spot("spot1", "スポット1", "テストスポット1")
        spot2 = Spot("spot2", "スポット2", "テストスポット2")
        spot3 = Spot("spot3", "スポット3", "テストスポット3")
        
        # グループに含まれるスポットを追加
        group.add_spot(spot1)
        group.add_spot(spot2)
        group.add_spot(spot3)  # グループに含まれないスポット
        
        assert len(group.spots) == 2
        assert "spot1" in group.spots
        assert "spot2" in group.spots
        assert "spot3" not in group.spots
        
        # 入り口スポットの確認
        assert len(group.entrance_spots) == 1
        assert "spot1" in group.entrance_spots
    
    def test_spot_group_methods(self):
        """SpotGroupの各種メソッドテスト"""
        config = SpotGroupConfig(
            group_id="test_group",
            name="テストグループ",
            description="テスト用のグループ",
            spot_ids=["spot1", "spot2"],
            entrance_spot_ids=["spot1"],
            exit_spot_ids=["spot2"],
            tags=["test"]
        )
        
        group = SpotGroup(config)
        spot1 = Spot("spot1", "スポット1", "テストスポット1")
        spot2 = Spot("spot2", "スポット2", "テストスポット2")
        
        group.add_spot(spot1)
        group.add_spot(spot2)
        
        # 各種メソッドのテスト
        assert group.get_spot("spot1") == spot1
        assert group.get_spot("spot3") is None
        assert len(group.get_all_spots()) == 2
        assert len(group.get_entrance_spots()) == 1
        assert len(group.get_exit_spots()) == 1
        assert group.has_spot("spot1") is True
        assert group.has_spot("spot3") is False
        assert group.is_entrance_spot("spot1") is True
        assert group.is_entrance_spot("spot2") is False
        assert group.is_exit_spot("spot2") is True
        assert group.is_exit_spot("spot1") is False
        assert group.has_tag("test") is True
        assert group.has_tag("demo") is False
        assert "test" in group.get_tags()
    
    def test_spot_group_summary(self):
        """SpotGroupの概要取得テスト"""
        config = SpotGroupConfig(
            group_id="test_group",
            name="テストグループ",
            description="テスト用のグループ",
            spot_ids=["spot1"],
            entrance_spot_ids=["spot1"],
            tags=["test"]
        )
        
        group = SpotGroup(config)
        spot1 = Spot("spot1", "スポット1", "テストスポット1")
        group.add_spot(spot1)
        
        summary = group.get_summary()
        assert "テストグループ" in summary
        assert "テスト用のグループ" in summary
        assert "スポット数: 1" in summary
        assert "入り口: spot1" in summary
        assert "タグ: test" in summary


class TestEntranceManager:
    """EntranceManagerのテスト"""
    
    def test_entrance_manager_creation(self):
        """EntranceManagerの作成テスト"""
        manager = EntranceManager()
        assert len(manager.entrances) == 0
        assert len(manager.group_entrances) == 0
        assert len(manager.locked_entrances) == 0
    
    def test_entrance_manager_add_entrance(self):
        """EntranceManagerへの出入り口追加テスト"""
        manager = EntranceManager()
        
        config = EntranceConfig(
            entrance_id="entrance1",
            name="テスト出入り口",
            description="テスト用の出入り口",
            from_group_id="group1",
            to_group_id="group2",
            from_spot_id="spot1",
            to_spot_id="spot2",
            is_bidirectional=True
        )
        
        manager.add_entrance(config)
        
        assert len(manager.entrances) == 1
        assert "entrance1" in manager.entrances
        assert len(manager.group_entrances) == 2
        assert "group1" in manager.group_entrances
        assert "group2" in manager.group_entrances
    
    def test_entrance_manager_methods(self):
        """EntranceManagerの各種メソッドテスト"""
        manager = EntranceManager()
        
        config = EntranceConfig(
            entrance_id="entrance1",
            name="テスト出入り口",
            description="テスト用の出入り口",
            from_group_id="group1",
            to_group_id="group2",
            from_spot_id="spot1",
            to_spot_id="spot2",
            is_bidirectional=True
        )
        
        manager.add_entrance(config)
        
        # 各種メソッドのテスト
        assert manager.get_entrance("entrance1") == config
        assert manager.get_entrance("entrance2") is None
        
        entrances = manager.get_entrances_for_group("group1")
        assert len(entrances) == 1
        assert entrances[0] == config
        
        entrances = manager.get_entrances_between_groups("group1", "group2")
        assert len(entrances) == 1
        assert entrances[0] == config
        
        entrance = manager.get_entrance_by_spots("spot1", "spot2")
        assert entrance == config
        
        assert manager.is_entrance_locked("entrance1") is False
    
    def test_entrance_manager_lock_unlock(self):
        """EntranceManagerのロック機能テスト"""
        manager = EntranceManager()
        
        config = EntranceConfig(
            entrance_id="entrance1",
            name="テスト出入り口",
            description="テスト用の出入り口",
            from_group_id="group1",
            to_group_id="group2",
            from_spot_id="spot1",
            to_spot_id="spot2",
            is_locked=True
        )
        
        manager.add_entrance(config)
        
        # 初期状態でロックされている
        assert manager.is_entrance_locked("entrance1") is True
        
        # ロック解除
        manager.unlock_entrance("entrance1")
        assert manager.is_entrance_locked("entrance1") is False
        
        # 再ロック
        manager.lock_entrance("entrance1")
        assert manager.is_entrance_locked("entrance1") is True


class TestMapBuilder:
    """MapBuilderのテスト"""
    
    def test_map_builder_creation(self):
        """MapBuilderの作成テスト"""
        builder = MapBuilder()
        assert len(builder.spots) == 0
        assert len(builder.groups) == 0
    
    def test_map_builder_from_config(self):
        """MapBuilderの設定からの構築テスト"""
        builder = MapBuilder()
        
        config = {
            "spots": [
                {"id": "spot1", "name": "スポット1", "description": "テストスポット1"},
                {"id": "spot2", "name": "スポット2", "description": "テストスポット2"}
            ],
            "groups": [
                {
                    "id": "group1",
                    "name": "グループ1",
                    "description": "テストグループ1",
                    "spot_ids": ["spot1", "spot2"],
                    "entrance_spot_ids": ["spot1"],
                    "tags": ["test"]
                }
            ],
            "connections": [
                {"from": "spot1", "to": "spot2", "description": "スポット1からスポット2へ"}
            ]
        }
        
        builder._build_from_config(config)
        
        assert len(builder.spots) == 2
        assert len(builder.groups) == 1
        assert len(builder.movement_graph.nodes) == 2
    
    def test_map_builder_json_loading(self):
        """MapBuilderのJSON読み込みテスト"""
        builder = MapBuilder()
        
        config = {
            "spots": [
                {"id": "spot1", "name": "スポット1", "description": "テストスポット1"}
            ],
            "groups": [
                {
                    "id": "group1",
                    "name": "グループ1",
                    "description": "テストグループ1",
                    "spot_ids": ["spot1"],
                    "tags": ["test"]
                }
            ]
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
            temp_file = f.name
        
        try:
            builder.load_from_json(temp_file)
            assert len(builder.spots) == 1
            assert len(builder.groups) == 1
        finally:
            os.unlink(temp_file)


class TestSpotManagerExtension:
    """SpotManager拡張機能のテスト"""
    
    def test_spot_manager_group_creation(self):
        """SpotManagerのグループ作成テスト"""
        spot_manager = SpotManager()
        
        config = SpotGroupConfig(
            group_id="test_group",
            name="テストグループ",
            description="テスト用のグループ",
            spot_ids=["spot1"],
            tags=["test"]
        )
        
        group = spot_manager.create_group(config)
        assert group.config.group_id == "test_group"
        assert len(spot_manager.groups) == 1
    
    def test_spot_manager_entrance_management(self):
        """SpotManagerの出入り口管理テスト"""
        spot_manager = SpotManager()
        
        entrance_config = EntranceConfig(
            entrance_id="entrance1",
            name="テスト出入り口",
            description="テスト用の出入り口",
            from_group_id="group1",
            to_group_id="group2",
            from_spot_id="spot1",
            to_spot_id="spot2"
        )
        
        spot_manager.add_entrance(entrance_config)
        
        entrance = spot_manager.get_entrance("entrance1")
        assert entrance == entrance_config
        
        assert spot_manager.is_entrance_locked("entrance1") is False
        
        spot_manager.lock_entrance("entrance1")
        assert spot_manager.is_entrance_locked("entrance1") is True
        
        spot_manager.unlock_entrance("entrance1")
        assert spot_manager.is_entrance_locked("entrance1") is False
    
    def test_spot_manager_map_validation(self):
        """SpotManagerのマップ整合性チェックテスト"""
        spot_manager = SpotManager()
        
        # 正常なマップ
        spot1 = Spot("spot1", "スポット1", "テストスポット1")
        spot2 = Spot("spot2", "スポット2", "テストスポット2")
        spot_manager.add_spot(spot1)
        spot_manager.add_spot(spot2)
        
        # 接続を追加して孤立を回避
        spot_manager.movement_graph.add_connection("spot1", "spot2", "スポット1からスポット2へ")
        
        config = SpotGroupConfig(
            group_id="test_group",
            name="テストグループ",
            description="テスト用のグループ",
            spot_ids=["spot1"],
            tags=["test"]
        )
        
        spot_manager.create_group(config)
        spot_manager.add_spot_to_group(spot1, "test_group")
        
        errors = spot_manager.validate_map()
        assert len(errors) == 0
        
        # エラーがあるマップ（存在しないスポットをグループに含める）
        error_config = SpotGroupConfig(
            group_id="error_group",
            name="エラーグループ",
            description="エラーテスト用のグループ",
            spot_ids=["nonexistent_spot"],
            tags=["test"]
        )
        
        spot_manager.create_group(error_config)
        
        errors = spot_manager.validate_map()
        assert len(errors) > 0
        assert any("存在しないスポット" in error for error in errors)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"]) 