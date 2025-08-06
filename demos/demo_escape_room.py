from typing import Dict, List, Optional
from game.core.game_context import GameContext, GameContextBuilder
from game.player.player import Player
from game.player.player_manager import PlayerManager
from game.world.spot import Spot
from game.world.spot_manager import SpotManager
from game.world.poi import POI, POIUnlockCondition
from game.world.poi_manager import POIManager
from game.item.item import Item
from game.enums import Role


class EscapeRoomDemo:
    def __init__(self):
        # ゲームコンテキストの初期化
        self.player_manager = PlayerManager()
        self.spot_manager = SpotManager()
        self.poi_manager = POIManager()
        self.game_context = GameContextBuilder()\
            .with_player_manager(self.player_manager)\
            .with_spot_manager(self.spot_manager)\
            .with_poi_manager(self.poi_manager)\
            .build()
        
        # プレイヤーの作成
        self.player = Player("player1", "探索者", Role.ADVENTURER)
        self.player_manager.add_player(self.player)
        
        # 部屋の作成
        self.room = Spot("escape_room", "密室", "あなたは見知らぬ部屋に閉じ込められた。出口を見つけ出さなければならない。")
        self.spot_manager.add_spot(self.room)
        self.player.set_current_spot_id("escape_room")
        
        # アイテムの作成
        self.red_key = Item("red_key", "赤い鍵", "赤く塗られた小さな鍵。")
        self.blue_key = Item("blue_key", "青い鍵", "青く塗られた小さな鍵。")
        self.green_key = Item("green_key", "緑の鍵", "緑色の小さな鍵。")
        
        # POIの作成と設定
        self._setup_pois()

    def _setup_pois(self):
        # 本棚POI
        bookshelf = POI(
            poi_id="bookshelf",
            name="本棚",
            description="古びた本棚。たくさんの本が並んでいる。",
            detailed_description="本を一冊抜き出すと、後ろから青い鍵が出てきた。"
        )
        bookshelf.add_item(self.blue_key)
        
        # 机POI
        desk = POI(
            poi_id="desk",
            name="机",
            description="木製の机。引き出しがある。",
            detailed_description="引き出しを開けると、赤い鍵が入っていた。"
        )
        desk.add_item(self.red_key)
        
        # 花瓶POI
        vase = POI(
            poi_id="vase",
            name="花瓶",
            description="大きな花瓶。中に何か入っているかもしれない。",
            detailed_description="花瓶の中をのぞくと、緑の鍵が沈んでいた。"
        )
        vase.add_item(self.green_key)
        
        # 出口POI（全ての鍵が必要）
        exit_door = POI(
            poi_id="exit_door",
            name="出口",
            description="3つの鍵穴がある頑丈なドア。",
            detailed_description="3つの鍵を差し込むと、ドアが開いた！脱出成功！",
            unlock_condition=POIUnlockCondition(
                required_items={"red_key", "blue_key", "green_key"}
            )
        )
        
        # POIを部屋に追加
        self.room.add_poi(bookshelf)
        self.room.add_poi(desk)
        self.room.add_poi(vase)
        self.room.add_poi(exit_door)
        
        # POIマネージャーに登録
        self.poi_manager.register_poi("escape_room", bookshelf)
        self.poi_manager.register_poi("escape_room", desk)
        self.poi_manager.register_poi("escape_room", vase)
        self.poi_manager.register_poi("escape_room", exit_door)

    def _print_status(self):
        """現在の状況を表示"""
        print("\n" + "="*50)
        print("現在の持ち物:")
        inventory = self.player.get_inventory()
        if inventory.get_items():
            for item in inventory.get_items():
                print(f"- {item.name}: {item.description}")
        else:
            print("何も持っていない")
        
        print("\n探索可能な場所:")
        available_pois = self.poi_manager.get_available_pois("escape_room", self.player)
        for i, poi in enumerate(available_pois, 1):
            print(f"{i}. {poi.name}: {poi.description}")
        
        print("\n探索済みの場所:")
        discovered_pois = self.poi_manager.get_discovered_pois("escape_room", self.player)
        for poi in discovered_pois:
            result = self.poi_manager.get_exploration_history("escape_room", poi.poi_id, self.player)
            if result:
                print(f"- {poi.name}: {result.description}")
        
        print("="*50 + "\n")

    def _get_player_choice(self, available_pois: List[POI]) -> Optional[str]:
        """プレイヤーの選択を取得"""
        while True:
            try:
                choice = input("探索する場所の番号を入力してください（0で終了）: ")
                if choice == "0":
                    return None
                choice_idx = int(choice) - 1
                if 0 <= choice_idx < len(available_pois):
                    return available_pois[choice_idx].poi_id
                print("無効な選択です。")
            except ValueError:
                print("無効な入力です。数字を入力してください。")

    def run(self):
        """ゲームを実行"""
        print("密室からの脱出")
        print(self.room.description)
        
        while True:
            self._print_status()
            
            # 探索可能なPOIを取得
            available_pois = self.poi_manager.get_available_pois("escape_room", self.player)
            if not available_pois:
                print("探索できる場所がありません。")
                break
            
            # プレイヤーの選択を取得
            poi_id = self._get_player_choice(available_pois)
            if poi_id is None:
                print("ゲームを終了します。")
                break
            
            # POIを探索
            result = self.poi_manager.explore_poi("escape_room", poi_id, self.player, self.game_context)
            print(f"\n{result.description}")
            
            if poi_id == "exit_door":
                print("おめでとうございます！脱出に成功しました！")
                break


if __name__ == "__main__":
    game = EscapeRoomDemo()
    game.run()