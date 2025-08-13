from typing import Dict, Optional, Any
import time
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
    def load_player_aggregate(self, player_id: int) -> Dict[str, Any]:
        """
        現行スキーマ（game/core/schema）に基づき、プレイヤー集約を読み込む。
        - player（ベース属性・ステータス・所持金・現在スポットIDなど）
        - player_location（最終更新位置）
        - player_inventory_stackable（スタック在庫）
        - player_inventory_unique + item_unique（ユニーク実体詳細）
        - player_equipment（装備中ユニーク）
        """

        # player
        player_rows = self._db.query(
            """
            SELECT player_id, name, role, hp, mp, level, experience, gold,
                   attack, defense, speed, max_hp, max_mp, state, current_spot_id, created_at
            FROM player
            WHERE player_id = ?
            """,
            (player_id,),
        )
        if not player_rows:
            raise ValueError(f"player not found: {player_id}")
        player_row = dict(player_rows[0])

        # location
        loc_rows = self._db.query(
            """
            SELECT spot_id, updated_at
            FROM player_location
            WHERE player_id = ?
            """,
            (player_id,),
        )
        location = dict(loc_rows[0]) if loc_rows else None

        # stacks
        stack_rows = self._db.query(
            """
            SELECT item_id, count
            FROM player_inventory_stackable
            WHERE player_id = ?
            """,
            (player_id,),
        )
        stacks: Dict[int, int] = {int(r["item_id"]): int(r["count"]) for r in stack_rows}

        # unique items
        unique_rows = self._db.query(
            """
            SELECT iu.unique_item_id, iu.item_id, iu.durability, iu.attack, iu.defense
            FROM item_unique iu
            JOIN player_inventory_unique pu ON pu.unique_item_id = iu.unique_item_id
            WHERE pu.player_id = ?
            """,
            (player_id,),
        )
        unique_items: Dict[int, Dict[str, Any]] = {
            int(r["unique_item_id"]): {
                "item_id": int(r["item_id"]),
                "durability": int(r["durability"]),
                "attack": None if r["attack"] is None else int(r["attack"]),
                "defense": None if r["defense"] is None else int(r["defense"]),
            }
            for r in unique_rows
        }

        # equipment
        equip_rows = self._db.query(
            """
            SELECT pe.slot, pe.unique_item_id, iu.item_id
            FROM player_equipment pe
            LEFT JOIN item_unique iu ON iu.unique_item_id = pe.unique_item_id
            WHERE pe.player_id = ?
            """,
            (player_id,),
        )
        equipment: Dict[str, Dict[str, Any]] = {}
        for r in equip_rows:
            equipment[str(r["slot"])] = {
                "unique_item_id": int(r["unique_item_id"]),
                "item_id": None if r["item_id"] is None else int(r["item_id"]),
            }

        return {
            "player": player_row,
            "location": location,
            "stacks": stacks,
            "unique_items": unique_items,
            "equipment": equipment,
        }

    def get_equipment(self, player_id: int) -> Dict[str, Dict[str, Any]]:
        """装備スロット -> {unique_item_id, item_id} の辞書を返す。"""
        rows = self._db.query(
            """
            SELECT pe.slot, pe.unique_item_id, iu.item_id
            FROM player_equipment pe
            LEFT JOIN item_unique iu ON iu.unique_item_id = pe.unique_item_id
            WHERE pe.player_id = ?
            """,
            (player_id,),
        )
        result: Dict[str, Dict[str, Any]] = {}
        for r in rows:
            result[str(r["slot"])] = {
                "unique_item_id": int(r["unique_item_id"]),
                "item_id": None if r["item_id"] is None else int(r["item_id"]),
            }
        return result

    # --- 書き込み（雛形） ---
    def increment_gold(self, player_id: int, delta: int) -> None:
        """所持金を増減（負残高は禁止）。条件付きUPDATEで担保。"""
        cur = self._db.execute(
            """
            UPDATE player
            SET gold = gold + ?
            WHERE player_id = ?
              AND gold + ? >= 0
            """,
            (delta, player_id, delta),
        )
        if cur.rowcount == 0:
            raise ValueError("failed to increment gold (insufficient funds or player not found)")

    def add_stack(self, player_id: int, item_id: int, delta: int) -> None:
        """スタック在庫を増減（0未満禁止）。INSERT/UPDATEで実現。"""
        if delta == 0:
            return
        if delta > 0:
            # 既存行があれば加算、なければ挿入
            cur = self._db.execute(
                """
                UPDATE player_inventory_stackable
                SET count = count + ?
                WHERE player_id = ? AND item_id = ?
                """,
                (delta, player_id, item_id),
            )
            if cur.rowcount == 0:
                self._db.execute(
                    """
                    INSERT INTO player_inventory_stackable (player_id, item_id, count)
                    VALUES (?, ?, ?)
                    """,
                    (player_id, item_id, delta),
                )
            return

        # delta < 0: 減算（在庫不足は失敗）
        cur = self._db.execute(
            """
            UPDATE player_inventory_stackable
            SET count = count + ?
            WHERE player_id = ? AND item_id = ?
              AND count + ? >= 0
            """,
            (delta, player_id, item_id, delta),
        )
        if cur.rowcount == 0:
            raise ValueError("insufficient stack or item not found")

    def upsert_equipment(
        self,
        player_id: int,
        slot: str,
        *,
        item_id: Optional[int] = None,
        unique_item_id: Optional[int] = None,
    ) -> None:
        """
        装備スロットにユニークアイテムをセット。
        現行スキーマでは player_equipment.unique_item_id のみを保持するため、unique_item_id が必須。
        """
        if item_id is not None:
            raise NotImplementedError("current schema supports only unique_item_id in player_equipment")
        if unique_item_id is None:
            raise ValueError("unique_item_id is required")

        # 所有チェック: player_inventory_unique に存在するか
        owner_rows = self._db.query(
            """
            SELECT 1
            FROM player_inventory_unique
            WHERE player_id = ? AND unique_item_id = ?
            """,
            (player_id, unique_item_id),
        )
        if not owner_rows:
            raise ValueError("player does not own the unique item")

        # UPSERT: PRIMARY KEY (player_id, slot)
        self._db.execute(
            """
            INSERT INTO player_equipment (player_id, slot, unique_item_id)
            VALUES (?, ?, ?)
            ON CONFLICT(player_id, slot)
            DO UPDATE SET unique_item_id = excluded.unique_item_id
            """,
            (player_id, slot, unique_item_id),
        )

    def clear_equipment(self, player_id: int, slot: str) -> None:
        """装備スロットを空にする（所持者テーブルからは削除しない）。"""
        self._db.execute(
            """
            DELETE FROM player_equipment
            WHERE player_id = ? AND slot = ?
            """,
            (player_id, slot),
        )

    def set_location(self, player_id: int, spot_id: str) -> None:
        """現在地をUPSERTで更新。"""
        now = int(time.time())
        self._db.execute(
            """
            INSERT INTO player_location (player_id, spot_id, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(player_id)
            DO UPDATE SET spot_id = excluded.spot_id, updated_at = excluded.updated_at
            """,
            (player_id, spot_id, now),
        )

    def update_appearance(self, player_id: int, slot: str, value: str) -> None:
        """外見設定を更新。現行スキーマでは player_appearance が未定義のため未対応。"""
        raise NotImplementedError("player_appearance table is commented out in current schema")
