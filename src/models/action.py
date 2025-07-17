class Action:
    def __init__(self, description: str):
        self.description = description

    def get_description(self) -> str:
        return self.description


class Movement(Action):
    def __init__(self, description: str, direction: str, target_spot_id: str):
        super().__init__(description)
        self.direction = direction
        self.target_spot_id = target_spot_id

    def get_direction(self) -> str:
        return self.direction

    def get_target_spot_id(self) -> str:
        return self.target_spot_id


class Exploration(Action):
    def __init__(self, description: str, item_id: str, discovered_info: str):
        super().__init__(description)
        self.item_id = item_id
        self.discovered_info = discovered_info

    def get_item_id(self) -> str:
        return self.item_id

    def get_discovered_info(self) -> str:
        return self.discovered_info

    def get_description(self) -> str:
        return self.description