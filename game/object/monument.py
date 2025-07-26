from game.object.interactable import InteractableObject


class Monument(InteractableObject):
    """石碑オブジェクト - 読み取り専用の歴史情報を持つ石碑"""
    
    def __init__(self, object_id: str, description: str, historical_text: str):
        super().__init__(object_id, description)
        self.historical_text = historical_text
        self.display_name = "石碑"
    
    def get_display_name(self) -> str:
        return self.display_name
    
    def read_historical_text(self) -> str:
        """石碑に刻まれた歴史的テキストを読み取る"""
        return self.historical_text
    
    def get_historical_text(self) -> str:
        """石碑の歴史的テキストを取得（読み取り専用）"""
        return self.historical_text 