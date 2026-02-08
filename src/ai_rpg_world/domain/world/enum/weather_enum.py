from enum import Enum


class WeatherTypeEnum(Enum):
    """天候の種類"""
    CLEAR = "CLEAR"        # 晴れ
    CLOUDY = "CLOUDY"      # 曇り
    RAIN = "RAIN"          # 雨
    HEAVY_RAIN = "HEAVY_RAIN" # 豪雨
    SNOW = "SNOW"          # 雪
    BLIZZARD = "BLIZZARD"  # 吹雪
    FOG = "FOG"            # 霧
    STORM = "STORM"        # 嵐
