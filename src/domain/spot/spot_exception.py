class SpotException(Exception):
    pass


class PlayerNotMeetConditionException(SpotException):
    pass


class PlayerAlreadyInSpotException(SpotException):
    pass


class PlayerNotInSpotException(SpotException):
    pass


class SpotNotConnectedException(SpotException):
    pass
    

class RoadNotConnectedToFromSpotException(SpotException):
    pass


class RoadNotConnectedToToSpotException(SpotException):
    pass