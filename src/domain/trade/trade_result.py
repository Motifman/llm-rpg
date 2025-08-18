from dataclasses import dataclass
from datetime import datetime
from src.domain.trade.trade_enum import TradeStatus
from typing import Optional


@dataclass
class TradeResult:
    """取引結果"""
    trade_id: int
    seller_id: int
    buyer_id: Optional[int]
    offered_item_id: int
    offered_item_count: Optional[int]
    offered_unique_id: Optional[int]
    requested_gold: int
    trade_status: TradeStatus
    created_at: datetime
    completed_at: Optional[datetime] = None
    
    def get_trade_summary(self) -> str:
        """取引の概要を取得"""
        if self.offered_item_count:
            item_desc = f"アイテム{self.offered_item_id} x{self.offered_item_count}"
        else:
            item_desc = f"アイテム{self.offered_item_id} (固有ID:{self.offered_unique_id})"
        
        status_str = {
            TradeStatus.ACTIVE: "募集中",
            TradeStatus.COMPLETED: "成立",
            TradeStatus.CANCELLED: "キャンセル"
        }.get(self.trade_status, "不明")
        
        return f"{item_desc} ⇄ {self.requested_gold}G [{status_str}]"
    
    def get_detailed_info(self) -> str:
        """詳細な取引情報を取得"""
        lines = [
            f"取引ID: {self.trade_id}",
            f"売り手ID: {self.seller_id}",
            f"買い手ID: {self.buyer_id or '未定'}",
            f"提示アイテム: {self.offered_item_id}",
        ]
        
        if self.offered_item_count:
            lines.append(f"アイテム数: {self.offered_item_count}")
        if self.offered_unique_id:
            lines.append(f"固有ID: {self.offered_unique_id}")
        
        lines.extend([
            f"要求金額: {self.requested_gold}G",
            f"ステータス: {self.trade_status.value}",
            f"作成時刻: {self.created_at.strftime('%Y-%m-%d %H:%M:%S')}"
        ])
        
        if self.completed_at:
            lines.append(f"成立時刻: {self.completed_at.strftime('%Y-%m-%d %H:%M:%S')}")
        
        return "\n".join(lines)
