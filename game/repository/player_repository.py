from typing import Dict, Optional
from game.core.database import Database


class PlayerRepository:
    """
    単一プレイヤー配下（status/inventory/equipment/appearance/location）を扱うアグリゲート・リポジトリ。
    ここではメソッドの最小シグネチャのみ定義し、実装は段階的に追加します。
    """

    def __init__(self, db: Database):
        self._db = db
        self._conn = db.conn
        self._cursor = self._conn.cursor()

    # --- 読み取り（雛形） ---
    def load_player_aggregate(self, player_id: str) -> Dict:
        """プレイヤー配下の集約情報をまとめて読み込む（雛形）。"""
        return {"player_id": player_id}

    def get_equipment(self, player_id: str) -> Dict[str, Dict]:
        """装備スロット情報を取得（雛形）。"""
        return {}

    # --- 書き込み（雛形） ---
    def increment_gold(self, player_id: str, delta: int) -> None:
        """所持金を増減（負残高は禁止。実装時に条件付きUPDATE）。"""
        pass

    def add_stack(self, player_id: str, item_id: str, delta: int) -> None:
        """スタック在庫を増減（0未満禁止。実装時にUPSERT/条件付きUPDATE）。"""
        pass

    def upsert_equipment(self, player_id: str, slot: str, *, item_id: Optional[str] = None, unique_item_id: Optional[str] = None) -> None:
        """装備スロットにセット（片方必須・排他。DB制約で保証）。"""
        pass

    def clear_equipment(self, player_id: str, slot: str) -> None:
        """装備スロットを空にする。"""
        pass

    def set_location(self, player_id: str, spot_id: str) -> None:
        """現在地を更新。"""
        pass

    def update_appearance(self, player_id: str, slot: str, value: str) -> None:
        """外見設定を更新。"""
        pass
