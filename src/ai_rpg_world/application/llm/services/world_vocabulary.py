"""enum の生値をプロンプトに出さないための呼び名を、1 か所に集める。

## なぜ集めるか

明るさの呼び名を共有定数に出したとき、**表と enum の対応を縛らなかった**。
その結果:

- ``LightingEnum`` は 4 件なのに表は 3 件で、``PITCH_BLACK`` だけ生値が出た。
  しかも夜 + 嵐の屋外で実際に到達する。**この仕組みが消しに来た生値が、
  一番暗いときにだけ残っていた**
- ``気温: WARM`` は 2 行下にあったのに手つかずだった
- 天候の呼び名が関数の中で組み立てられ、別モジュールにも同じ表があった

どれも「表を作ったが、抜けを検出する仕組みが無い」1 つの形。#922 で
``PromptSection`` / ``GamePhase`` に付けた網羅テストと同じものを、表示辞書
にも付ける (claude の指摘)。

## 語尾を変えたい場所は別に持ってよい

``interaction_condition_hint_text`` は「暗い場所のみ」のように文へ埋める
ので、語尾が違う表を持っている。**それは統合しない。** ただし
**キーの集合は同じでなければならない**ので、走査は同じ enum から引く。
"""

from __future__ import annotations

from typing import Any, Dict, Mapping

from ai_rpg_world.domain.world.enum.weather_enum import WeatherTypeEnum
from ai_rpg_world.domain.world_graph.enum.lighting_enum import LightingEnum
from ai_rpg_world.domain.world_graph.enum.temperature_enum import TemperatureEnum

#: 明るさ。``LightingEnum`` の全件を載せる (網羅テストが縛る)。
LIGHTING_DISPLAY: Dict[str, str] = {
    LightingEnum.BRIGHT.value: "明るい",
    LightingEnum.DIM.value: "薄暗い",
    LightingEnum.DARK.value: "暗い",
    LightingEnum.PITCH_BLACK.value: "真っ暗",
}

#: 気温。``TemperatureEnum`` の全件を載せる。
TEMPERATURE_DISPLAY: Dict[str, str] = {
    TemperatureEnum.FREEZING.value: "凍える寒さ",
    TemperatureEnum.COLD.value: "寒い",
    TemperatureEnum.NORMAL.value: "過ごしやすい",
    TemperatureEnum.WARM.value: "暖かい",
    TemperatureEnum.HOT.value: "暑い",
}

#: 天候。``WeatherType`` の全件を載せる。
WEATHER_DISPLAY: Dict[str, str] = {
    WeatherTypeEnum.CLEAR.value: "晴れ",
    WeatherTypeEnum.CLOUDY.value: "曇り",
    WeatherTypeEnum.RAIN.value: "雨",
    WeatherTypeEnum.HEAVY_RAIN.value: "大雨",
    WeatherTypeEnum.SNOW.value: "雪",
    WeatherTypeEnum.BLIZZARD.value: "吹雪",
    WeatherTypeEnum.FOG.value: "霧",
    WeatherTypeEnum.STORM.value: "嵐",
}

#: 網羅テストが見る (enum, 表) の組。**表を足したらここにも足す。**
DISPLAY_TABLES: tuple = (
    (LightingEnum, LIGHTING_DISPLAY),
    (TemperatureEnum, TEMPERATURE_DISPLAY),
    (WeatherTypeEnum, WEATHER_DISPLAY),
)


def _display(table: Mapping[str, str], value: Any) -> str:
    """呼び名を返す。**知らない値はそのまま返さない。**

    生値を返すと「表に載せ忘れた」ことが誰にも見えないまま、プロンプトへ
    enum が漏れ続ける。網羅テストが載せ忘れを落とすので、ここに来る未知の
    値は enum 自体が増えた場合に限る。そのときは空にして、**行ごと薄くなる
    ほうが、生値が出るよりまし**。
    """
    key = getattr(value, "value", value)
    return table.get(str(key), "")


def lighting_display(value: Any) -> str:
    """明るさの呼び名。"""
    return _display(LIGHTING_DISPLAY, value)


def temperature_display(value: Any) -> str:
    """気温の呼び名。"""
    return _display(TEMPERATURE_DISPLAY, value)


def weather_display(value: Any) -> str:
    """天候の呼び名。"""
    return _display(WEATHER_DISPLAY, value)
