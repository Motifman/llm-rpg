"""Spot Graph ドメインの例外定義"""

from ai_rpg_world.domain.common.exception import (
    BusinessRuleException,
    DomainException,
    ValidationException,
)


class SpotGraphDomainException(DomainException):
    """Spot Graph ドメインの基底例外"""

    domain = "world_graph"


class EntityIdValidationException(SpotGraphDomainException, ValidationException):
    """エンティティIDバリデーション例外"""
    error_code = "WORLD_GRAPH.ENTITY_ID_VALIDATION"


class ConnectionIdValidationException(SpotGraphDomainException, ValidationException):
    """接続IDバリデーション例外"""
    error_code = "WORLD_GRAPH.CONNECTION_ID_VALIDATION"


class SpotGraphIdValidationException(SpotGraphDomainException, ValidationException):
    """スポットグラフ集約IDバリデーション例外"""
    error_code = "WORLD_GRAPH.GRAPH_ID_VALIDATION"


class SpotNotInGraphException(SpotGraphDomainException, BusinessRuleException):
    """グラフに存在しないスポットを参照した"""
    error_code = "WORLD_GRAPH.SPOT_NOT_IN_GRAPH"


class UnknownConnectionException(SpotGraphDomainException, BusinessRuleException):
    """未知の接続ID"""
    error_code = "WORLD_GRAPH.UNKNOWN_CONNECTION"


class EntityNotInGraphException(SpotGraphDomainException, BusinessRuleException):
    """エンティティがグラフ上に配置されていない"""
    error_code = "WORLD_GRAPH.ENTITY_NOT_IN_GRAPH"


class EntityNotAtSpotException(SpotGraphDomainException, BusinessRuleException):
    """エンティティが期待したスポットにいない"""
    error_code = "WORLD_GRAPH.ENTITY_NOT_AT_SPOT"


class ConnectionNotPassableException(SpotGraphDomainException, BusinessRuleException):
    """接続が通行不能（閉鎖または条件未満足）"""
    error_code = "WORLD_GRAPH.CONNECTION_NOT_PASSABLE"


class DuplicateSpotException(SpotGraphDomainException, BusinessRuleException):
    """同一スポットIDの重複登録"""
    error_code = "WORLD_GRAPH.DUPLICATE_SPOT"


class DuplicateConnectionIdException(SpotGraphDomainException, BusinessRuleException):
    """接続IDの重複"""
    error_code = "WORLD_GRAPH.DUPLICATE_CONNECTION_ID"


class SpotPresenceInvariantException(SpotGraphDomainException, BusinessRuleException):
    """在席情報の不整合"""
    error_code = "WORLD_GRAPH.PRESENCE_INVARIANT"


class MonsterNotInGraphException(SpotGraphDomainException, BusinessRuleException):
    """モンスターがグラフ上に配置されていない"""
    error_code = "WORLD_GRAPH.MONSTER_NOT_IN_GRAPH"


class MonsterPresenceInvariantException(SpotGraphDomainException, BusinessRuleException):
    """モンスター在席情報の不整合（重複配置・未配置に対する除去 等）"""
    error_code = "WORLD_GRAPH.MONSTER_PRESENCE_INVARIANT"


class SubLocationIdValidationException(SpotGraphDomainException, ValidationException):
    """サブロケーションIDバリデーション例外"""
    error_code = "WORLD_GRAPH.SUB_LOCATION_ID_VALIDATION"


class SpotObjectIdValidationException(SpotGraphDomainException, ValidationException):
    """スポットオブジェクトIDバリデーション例外"""
    error_code = "WORLD_GRAPH.SPOT_OBJECT_ID_VALIDATION"


class SpotObjectValidationException(SpotGraphDomainException, ValidationException):
    """SpotObject エンティティのバリデーション例外"""
    error_code = "WORLD_GRAPH.SPOT_OBJECT_VALIDATION"


class PredicateResultValidationException(
    SpotGraphDomainException, ValidationException
):
    """述語評価結果の成立可否と失敗情報が矛盾している。"""

    error_code = "WORLD_GRAPH.PREDICATE_RESULT_VALIDATION"


class ScenarioPredicateValidationException(
    SpotGraphDomainException, ValidationException
):
    """共通シナリオ述語の定義が不正である。"""

    error_code = "WORLD_GRAPH.SCENARIO_PREDICATE_VALIDATION"


class PredicateContextValidationException(
    SpotGraphDomainException, ValidationException
):
    """共通述語へ渡す評価文脈の型が不正である。"""

    error_code = "WORLD_GRAPH.PREDICATE_CONTEXT_VALIDATION"


class ScenarioPredicateEvaluationException(
    SpotGraphDomainException, BusinessRuleException
):
    """述語評価が入力不足または評価器の未対応により完了できない。"""

    error_code = "WORLD_GRAPH.SCENARIO_PREDICATE_EVALUATION"


class StateDisplayRuleValidationException(SpotGraphDomainException, ValidationException):
    """オブジェクト state の prompt 表示ルールのバリデーション例外"""
    error_code = "WORLD_GRAPH.STATE_DISPLAY_RULE_VALIDATION"


class UnknownSpotObjectException(SpotGraphDomainException, BusinessRuleException):
    """スポット内に存在しないオブジェクトを参照した"""
    error_code = "WORLD_GRAPH.UNKNOWN_SPOT_OBJECT"


class InteractionNotFoundException(SpotGraphDomainException, BusinessRuleException):
    """指定した操作名のインタラクションがない"""
    error_code = "WORLD_GRAPH.INTERACTION_NOT_FOUND"


class InteractionNotAllowedException(SpotGraphDomainException, BusinessRuleException):
    """インタラクションの前提条件を満たしていない。

    ``failed_condition`` に**どの条件で落ちたか**を載せる (#380)。載せない場合は
    ``None`` で、既存の 1 引数 raise はそのまま動く。

    ## なぜ条件そのものを運ぶか

    判定した瞬間は条件の種別・対象・要求値を確実に知っているのに、以前は
    ``(False, failure_message)`` の文字列だけを返して型を捨てていた。そして
    application 層が**その日本語を部分一致検索して型を当て直していた**。

    捨てた情報を渡せば推測は要らない。詳細は
    `application/world_graph/precondition_failure_kind.py`。
    """
    error_code = "WORLD_GRAPH.INTERACTION_NOT_ALLOWED"

    def __init__(self, *args, failed_condition=None) -> None:
        super().__init__(*args)
        self.failed_condition = failed_condition


class UnsupportedInteractionEffectException(SpotGraphDomainException, BusinessRuleException):
    """未対応の interaction effect が指定された"""
    error_code = "WORLD_GRAPH.UNSUPPORTED_INTERACTION_EFFECT"


class InteractionEffectValidationException(SpotGraphDomainException, ValidationException):
    """interaction effect の指定が、適用時の文脈と噛み合っていない。

    ``target=TARGET_PLAYER`` の effect が、対象プレイヤーを渡していない
    呼び出しに来た場合など。行為者へフォールバックさせると「奪ったつもりで
    自分の持ち物が消える」ような、成功として返る誤動作になるので拒否する。
    """
    error_code = "WORLD_GRAPH.INTERACTION_EFFECT_VALIDATION"


class SpotTravelUnreachableException(SpotGraphDomainException, BusinessRuleException):
    """指定スポットへの経路が存在しない（または到達不能）"""
    error_code = "WORLD_GRAPH.SPOT_TRAVEL_UNREACHABLE"


class SpotTravelAlreadyInProgressException(SpotGraphDomainException, BusinessRuleException):
    """既にスポット間移動中のときに再度移動開始しようとした"""
    error_code = "WORLD_GRAPH.SPOT_TRAVEL_ALREADY_IN_PROGRESS"


class DayNightPhaseValidationException(SpotGraphDomainException, ValidationException):
    """昼夜サイクルのフェーズ定義バリデーション例外"""
    error_code = "WORLD_GRAPH.DAY_NIGHT_PHASE_VALIDATION"


class DayNightCycleValidationException(SpotGraphDomainException, ValidationException):
    """昼夜サイクル定義バリデーション例外"""
    error_code = "WORLD_GRAPH.DAY_NIGHT_CYCLE_VALIDATION"


class TimeOfDayValidationException(SpotGraphDomainException, ValidationException):
    """TimeOfDay 値オブジェクトのバリデーション例外"""
    error_code = "WORLD_GRAPH.TIME_OF_DAY_VALIDATION"


class PassageValidationException(SpotGraphDomainException, ValidationException):
    """Passage 値オブジェクトおよび SpotConnection の通過形態関連バリデーション例外"""
    error_code = "WORLD_GRAPH.PASSAGE_VALIDATION"


class SpotPositionValidationException(SpotGraphDomainException, ValidationException):
    """SpotPosition 値オブジェクトのバリデーション例外"""
    error_code = "WORLD_GRAPH.SPOT_POSITION_VALIDATION"


class SpotConnectionValidationException(SpotGraphDomainException, ValidationException):
    """SpotConnection エンティティのバリデーション例外"""
    error_code = "WORLD_GRAPH.SPOT_CONNECTION_VALIDATION"


class SynchronizedActionGroupValidationException(
    SpotGraphDomainException, ValidationException
):
    """SynchronizedActionGroup のバリデーション例外"""
    error_code = "WORLD_GRAPH.SYNCHRONIZED_ACTION_GROUP_VALIDATION"


class ReactiveObjectStateBindingValidationException(
    SpotGraphDomainException, ValidationException
):
    """ReactiveObjectStateBinding のバリデーション例外"""
    error_code = "WORLD_GRAPH.REACTIVE_OBJECT_STATE_BINDING_VALIDATION"


class GameEndConditionValidationException(
    SpotGraphDomainException, ValidationException
):
    """GameEndCondition のバリデーション例外"""
    error_code = "WORLD_GRAPH.GAME_END_CONDITION_VALIDATION"


class PlayerOutcomeRuleValidationException(
    SpotGraphDomainException, ValidationException
):
    """PlayerOutcomeRule の宣言不変条件違反。"""

    error_code = "WORLD_GRAPH.PLAYER_OUTCOME_RULE_VALIDATION"


class GamePhaseTransitionException(
    SpotGraphDomainException, BusinessRuleException
):
    """フェーズ遷移の不変条件違反。

    「会議中にもう一度招集する」「自由時間で会議を終わらせる」のように、
    現在のフェーズから起こしえない遷移を要求されたときに投げる。

    1 tick 内で全プレイヤーが並列に行動するので、2 人が同じ tick に緊急
    ボタンを押すことは実際に起こりうる。application 層はこれを捕まえて
    「会議はもう始まっている」という学習可能な失敗に変換する。
    """
    error_code = "WORLD_GRAPH.GAME_PHASE_TRANSITION"
