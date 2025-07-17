class Item:
    def __init__(self, item_id: str, name: str, description: str):
        self.item_id = item_id
        self.name = name
        self.description = description

    def __str__(self):
        return f"{self.name} - {self.description}"
    
    def __repr__(self):
        return f"Item(item_id={self.item_id}, name={self.name}, description={self.description})"