class SpotException(Exception):
    pass


class PlayerNotMeetConditionException(SpotException):
    pass


class PlayerAlreadyInToSpotException(SpotException):
    pass


class PlayerNotInFromSpotException(SpotException):
    pass


class SpotNotConnectedException(SpotException):
    pass
    

class RoadNotConnectedToFromSpotException(SpotException):
    pass


class RoadNotConnectedToToSpotException(SpotException):
    pass