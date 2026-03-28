"""Application-layer exceptions for scene visualization support."""

from ai_rpg_world.application.common.exceptions import ApplicationException


class GameSceneNotFoundException(ApplicationException):
    def __init__(self, spot_id: int):
        super().__init__(f"Game scene not found for spot_id={spot_id}", spot_id=spot_id)


class TiledImportException(ApplicationException):
    def __init__(self, message: str, **context):
        super().__init__(message, **context)


class ManualControlForbiddenException(ApplicationException):
    def __init__(self, player_id: int):
        super().__init__(
            f"Manual control is not allowed for player_id={player_id}",
            player_id=player_id,
        )


class SimulationSpeedValidationException(ApplicationException):
    def __init__(self, speed_multiplier: float):
        super().__init__(
            f"speed_multiplier must be greater than 0: {speed_multiplier}",
            speed_multiplier=speed_multiplier,
        )
