"""ゲートウェイ遷移条件の値オブジェクト。追加条件は同パターンで拡張する。"""

from dataclasses import dataclass

from ai_rpg_world.domain.world.enum.weather_enum import WeatherTypeEnum


@dataclass(frozen=True)
class TransitionCondition:
    """遷移条件の基底（マーカー）。具象は RequireRelation / RequireToll / BlockIfWeather 等。"""
    pass


@dataclass(frozen=True)
class RequireRelation(TransitionCondition):
    """関係者のみ許可（例: 王城前はギルドメンバー・クエスト関係者のみ）"""
    relation_type: str


@dataclass(frozen=True)
class RequireToll(TransitionCondition):
    """通行料が必要。許可時の支払い実行は別ユースケースで行う。"""
    amount_gold: int
    recipient_type: str = "spot"
    recipient_id: str | None = None


@dataclass(frozen=True)
class BlockIfWeather(TransitionCondition):
    """指定天候では通行不可（例: 沼地＋悪天候で通行止め）"""
    blocked_weather_types: tuple[WeatherTypeEnum, ...]


def block_if_weather(weather_types: list[WeatherTypeEnum]) -> BlockIfWeather:
    """BlockIfWeather を生成するヘルパー"""
    return BlockIfWeather(blocked_weather_types=tuple(weather_types))
