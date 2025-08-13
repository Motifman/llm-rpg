import pytest

from game.action.action_orchestrator import ActionOrchestrator
from game.core.game_context import GameContext
from game.player.player_manager import PlayerManager
from game.world.spot_manager import SpotManager
from game.world.spot import Spot
from game.player.player import Player
from game.enums import Role, AppearanceSlot
from game.item.item import AppearanceItem


class TestClothingActions:
    def setup_method(self):
        self.player_manager = PlayerManager()
        self.spot_manager = SpotManager()
        self.game_context = GameContext(self.player_manager, self.spot_manager)
        self.orchestrator = ActionOrchestrator(self.game_context)

        # プレイヤーとスポット
        self.player = Player("p1", "テスト", Role.CITIZEN)
        self.player_manager.add_player(self.player)
        self.spot = Spot("s1", "スポット1", "説明")
        self.spot_manager.add_spot(self.spot)
        self.player.set_current_spot_id("s1")

    def test_candidates_include_clothing_actions(self):
        cands = self.orchestrator.get_action_candidates_for_llm("p1")
        names = [c['action_name'] for c in cands]
        assert "見た目確認" in names
        assert "服飾装着" in names
        assert "服飾解除" in names

    def test_equip_and_unequip_clothing(self):
        # 服飾アイテム追加
        hat = AppearanceItem(item_id="hat_simple", name="帽子", description="布の帽子", slot=AppearanceSlot.HEADWEAR, appearance_text="小さな帽子")
        self.player.add_item(hat)
        assert self.player.get_inventory_item_count("hat_simple") == 1

        # 装着
        result = self.orchestrator.execute_llm_action("p1", "服飾装着", {"item_id": "hat_simple"})
        assert result.success is True
        assert self.player.get_inventory_item_count("hat_simple") == 0
        assert self.player.appearance.get_equipped(AppearanceSlot.HEADWEAR) is not None

        # 解除
        result2 = self.orchestrator.execute_llm_action("p1", "服飾解除", {"slot_name": AppearanceSlot.HEADWEAR.value})
        assert result2.success is True
        assert self.player.get_inventory_item_count("hat_simple") == 1
        assert self.player.appearance.get_equipped(AppearanceSlot.HEADWEAR) is None

    def test_appearance_check_text(self):
        self.player.set_base_appearance("黒髪の青年")
        top = AppearanceItem(item_id="top_shirt", name="シャツ", description="白いシャツ", slot=AppearanceSlot.TOP, appearance_text="白いシャツ")
        self.player.add_item(top)
        self.orchestrator.execute_llm_action("p1", "服飾装着", {"item_id": "top_shirt"})

        result = self.orchestrator.execute_llm_action("p1", "見た目確認", {})
        assert result.success is True
        # 直接フィールドで確認
        assert hasattr(result, 'appearance_text')
        assert "黒髪の青年" in result.appearance_text
        assert "top: 白いシャツ" in result.appearance_text


