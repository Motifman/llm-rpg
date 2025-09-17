class BattleActionException(Exception):
    """戦闘行動実行時の例外"""
    pass

class InsufficientMpException(BattleActionException):
    """MP不足例外"""
    pass

class InsufficientHpException(BattleActionException):
    """HP不足例外"""
    pass

class SilencedException(BattleActionException):
    """沈黙状態例外"""
    pass

class BlindedException(BattleActionException):
    """暗闇状態例外"""
    pass

class BattleAlreadyExistsException(Exception):
    """戦闘が既に存在する例外"""
    pass

class AreaNotFoundException(Exception):
    """エリアが見つからない例外"""
    pass

class BattleNotFoundException(Exception):
    """戦闘が見つからない例外"""
    pass

class BattleNotStartedException(Exception):
    """戦闘が開始されていない例外"""
    pass

class BattleFullException(Exception):
    """戦闘が満員の例外"""
    pass

class PlayerAlreadyInBattleException(Exception):
    """プレイヤーが既に戦闘に参加している例外"""
    pass


class ActorNotFoundException(Exception):
    """アクターが見つからない例外"""
    pass