from ai_rpg_world.game_world.domain.exception.game_world_exception import GameWorldDomainException, WorldRefusal


class EmptyRouteException(GameWorldDomainException):
    error_code = "GAME_WORLD.WHEREABOUTS.EMPTY_ROUTE"


class BrokenRouteException(GameWorldDomainException):
    error_code = "GAME_WORLD.WHEREABOUTS.BROKEN_ROUTE"


class UnknownPassageException(GameWorldDomainException):
    error_code = "GAME_WORLD.WHEREABOUTS.UNKNOWN_PASSAGE"


class PassageAlreadyRemovedException(WorldRefusal):
    error_code = "GAME_WORLD.WHEREABOUTS.PASSAGE_ALREADY_REMOVED"


class UnknownSpotException(GameWorldDomainException):
    error_code = "GAME_WORLD.WHEREABOUTS.UNKNOWN_SPOT"


class OccupantAlreadyPlacedException(GameWorldDomainException):
    error_code = "GAME_WORLD.WHEREABOUTS.OCCUPANT_ALREADY_PLACED"


class OccupantNotPlacedException(GameWorldDomainException):
    error_code = "GAME_WORLD.WHEREABOUTS.OCCUPANT_NOT_PLACED"


class OccupantNotAtRouteStartException(WorldRefusal):
    error_code = "GAME_WORLD.WHEREABOUTS.OCCUPANT_NOT_AT_ROUTE_START"


class OccupantNotStandingOnSpotException(GameWorldDomainException):
    error_code = "GAME_WORLD.WHEREABOUTS.OCCUPANT_NOT_STANDING_ON_SPOT"


class OccupantNotTravellingException(GameWorldDomainException):
    error_code = "GAME_WORLD.WHEREABOUTS.OCCUPANT_NOT_TRAVELLING"


class OccupantNotAtSectionSpotException(WorldRefusal):
    error_code = "GAME_WORLD.WHEREABOUTS.OCCUPANT_NOT_AT_SECTION_SPOT"


class OccupantAlreadyInSectionException(WorldRefusal):
    error_code = "GAME_WORLD.WHEREABOUTS.OCCUPANT_ALREADY_IN_SECTION"


class OccupantNotInSectionException(WorldRefusal):
    error_code = "GAME_WORLD.WHEREABOUTS.OCCUPANT_NOT_IN_SECTION"


class NoRouteToDestinationException(WorldRefusal):
    error_code = "GAME_WORLD.WHEREABOUTS.NO_ROUTE"


class SectionFullException(WorldRefusal):
    error_code = "GAME_WORLD.WHEREABOUTS.SECTION_FULL"


class TravelPositionOutsideRouteException(GameWorldDomainException):
    error_code = "GAME_WORLD.WHEREABOUTS.TRAVEL_POSITION_OUTSIDE_ROUTE"


class TravelNotDepartedFromPassageStartException(GameWorldDomainException):
    error_code = "GAME_WORLD.WHEREABOUTS.TRAVEL_NOT_DEPARTED_FROM_PASSAGE_START"


class TicksLeftOutsidePassageException(GameWorldDomainException):
    error_code = "GAME_WORLD.WHEREABOUTS.TICKS_LEFT_OUTSIDE_PASSAGE"


class PassageNotDeclaredHiddenException(GameWorldDomainException):
    error_code = "GAME_WORLD.WHEREABOUTS.PASSAGE_NOT_DECLARED_HIDDEN"
