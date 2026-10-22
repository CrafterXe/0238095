"""实时环境信息：日期/星期/时段（本地）+ 天气（open-meteo 免费无 key，30 分钟缓存）。

联网失败自动降级：只少天气一句，不影响对话。
"""
import time
from datetime import datetime

import requests

import config

_WEEK = ["一", "二", "三", "四", "五", "六", "日"]
_WMO = {0: "晴", 1: "基本晴", 2: "多云", 3: "阴", 45: "雾", 48: "雾凇",
        51: "毛毛雨", 53: "小雨", 55: "密雨", 61: "小雨", 63: "中雨", 65: "大雨",
        71: "小雪", 73: "中雪", 75: "大雪", 80: "阵雨", 81: "阵中雨", 82: "阵暴雨",
        95: "雷阵雨", 96: "雷阵雨伴冰雹", 99: "雷暴冰雹"}

_cache = {"ts": 0.0, "text": None}


def _weather() -> str:
    if time.time() - _cache["ts"] < 1800:
        return _cache["text"] or ""
    try:
        r = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={"latitude": config.WEATHER_LAT, "longitude": config.WEATHER_LON,
                    "current": "temperature_2m,weather_code",
                    "timezone": "auto", "forecast_days": "1"},
            timeout=config.WEATHER_TIMEOUT)
        cur = r.json()["current"]
        desc = _WMO.get(int(cur["weather_code"]), "天气未知")
        text = f"{config.WEATHER_CITY}{desc}，{round(cur['temperature_2m'])}°C"
    except Exception:
        text = ""
    _cache["ts"] = time.time()
    _cache["text"] = text
    return text


def _period(h: int) -> str:
    if 5 <= h < 8:
        return "清晨"
    if 8 <= h < 11:
        return "上午"
    if 11 <= h < 13:
        return "中午"
    if 13 <= h < 17:
        return "下午"
    if 17 <= h < 19:
        return "傍晚"
    if 19 <= h < 23:
        return "晚上"
    return "深夜"


def context_line() -> str:
    now = datetime.now()
    line = f"今天是{now.year}年{now.month}月{now.day}日，星期{_WEEK[now.weekday()]}，{now:%H:%M}（{_period(now.hour)}）。"
    w = _weather()
    if w:
        line += f"现在{w}。"
    return line
