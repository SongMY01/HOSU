"""
기상청 실시간 체감온도 어댑터

MCP 서버가 호출 시점에 실시간으로 부르는 유일한 외부 소스.
KMA_API_KEY 환경변수가 있으면 기상청 단기예보 실황 API를 호출하고,
없으면 결정론적 폴백값을 반환해 개발/데모가 끊기지 않게 한다.

폭염 단계 구분은 기상청 체감온도 기준을 따른다.
  관심 <31 / 주의 31~33 / 경고 33~35 / 위험 >=35
"""

import csv
import os
from datetime import datetime, timedelta
from urllib.parse import unquote
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WEATHER_CSV_PATH = os.path.join(BASE_DIR, "data", "raw", "gyeongbuk_weather.csv")

_raw_kma_key = os.environ.get("KMA_API_KEY") or os.environ.get("DATA_GO_KR_SERVICE_KEY", "")
KMA_API_KEY = unquote(_raw_kma_key) if _raw_kma_key else None
KMA_URL = ("https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getUltraSrtNcst")

LEVEL_SCORE = {"관심": 20.0, "주의": 50.0, "경고": 75.0, "위험": 100.0}

_cache = {}
CACHE_TTL_SEC = 600  # 10분

# gyeongbuk_weather.csv 데이터 로드
_weather_by_grid = {}
_weather_by_emd_code = {}
_weather_by_name = {}


def _load_local_weather_csv():
    global _weather_by_grid, _weather_by_emd_code, _weather_by_name
    if not os.path.exists(WEATHER_CSV_PATH):
        return
    with open(WEATHER_CSV_PATH, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            try:
                nx = int(float(r["grid_nx"]))
                ny = int(float(r["grid_ny"]))
                temp = float(r["temperature"])
                hum = float(r["humidity"])
                feels = float(r["feels_like"])
                tier = r.get("risk_tier", "관심")
                ann = r.get("announce_time", "")
                emd_code = r.get("emd_code", "").strip()
                sgg = r.get("sigungu_name", "").strip()
                emd = r.get("emd_name", "").strip()

                wdata = {
                    "emd_code": emd_code,
                    "sigungu": sgg,
                    "eupmyeondong": emd,
                    "grid_nx": nx,
                    "grid_ny": ny,
                    "temperature": temp,
                    "humidity": hum,
                    "feels_like": feels,
                    "risk_tier": tier,
                    "announce_time": ann,
                }

                _weather_by_grid[(nx, ny)] = wdata
                if emd_code:
                    _weather_by_emd_code[emd_code] = wdata
                if sgg and emd:
                    _weather_by_name[(sgg, emd)] = wdata
            except (ValueError, KeyError):
                continue


_load_local_weather_csv()


def temp_to_level(feels_like_c: float) -> str:
    if feels_like_c >= 35:
        return "위험"
    if feels_like_c >= 33:
        return "경고"
    if feels_like_c >= 31:
        return "주의"
    return "관심"


def _calc_feels_like(temp_c: float, humidity_pct: float) -> float:
    """기상청 공식 여름철 체감온도 산출 공식 (Stull 습구온도 기반)."""
    import math
    ta = float(temp_c)
    rh = float(humidity_pct)
    tw = ta * math.atan(0.151977 * math.sqrt(rh + 8.313659)) + \
         math.atan(ta + rh) - math.atan(rh - 1.676331) + \
         0.00391838 * (rh ** 1.5) * math.atan(0.023101 * rh) - 4.686035
    feels = -0.2442 + (0.55399 * tw) + (0.45535 * ta) - (0.0022 * (tw ** 2)) + (0.00278 * tw * ta) + 3.0
    return round(feels, 1)


def _fallback(nx: int, ny: int) -> float:
    """로컬 CSV 실측 데이터 확인 후 없으면 결정론적 계산."""
    if (nx, ny) in _weather_by_grid:
        return _weather_by_grid[(nx, ny)]["feels_like"]

    seed = (nx * 31 + ny * 17) % 100
    hour = datetime.now().hour
    diurnal = 6.0 * max(0.0, 1 - abs(hour - 15) / 9)  # 15시 피크
    return round(27.0 + seed / 100 * 7.0 + diurnal, 1)


def get_weather_details(nx: int, ny: int, region_code: str = None, sigungu: str = None, eupmyeondong: str = None) -> dict:
    """격자 좌표 및 지역 정보에 해당하는 상세 기상 정보(기온, 습도, 체감온도, 발표시각) 반환."""
    # 1. emd_code 매칭
    if region_code and region_code in _weather_by_emd_code:
        return _weather_by_emd_code[region_code]

    # 2. (sigungu, eupmyeondong) 매칭
    if sigungu and eupmyeondong and (sigungu, eupmyeondong) in _weather_by_name:
        return _weather_by_name[(sigungu, eupmyeondong)]

    # 3. (nx, ny) 격자 매칭
    if (nx, ny) in _weather_by_grid:
        return _weather_by_grid[(nx, ny)]

    # 4. 폴백 계산
    feels = get_feels_like(nx, ny)
    return {
        "temperature": feels - 2.5,
        "humidity": 75.0,
        "feels_like": feels,
        "risk_tier": temp_to_level(feels),
        "announce_time": datetime.now().strftime("%Y%m%dT%H:00")
    }


def get_feels_like(nx: int, ny: int) -> float:
    """격자 좌표의 현재 체감온도(도). 10분 캐시."""
    key = (nx, ny)
    now = datetime.now()
    if key in _cache:
        ts, val = _cache[key]
        if (now - ts).total_seconds() < CACHE_TTL_SEC:
            return val

    # 로컬 CSV 실측 데이터 우선 적용
    if (nx, ny) in _weather_by_grid:
        val = _weather_by_grid[(nx, ny)]["feels_like"]
    else:
        val = _fetch_kma(nx, ny) if KMA_API_KEY else _fallback(nx, ny)

    _cache[key] = (now, val)
    return val


def _fetch_kma(nx: int, ny: int) -> float:
    """기상청 초단기실황 조회. 실패 시 폴백으로 degrade."""
    try:
        import requests
    except ImportError:
        return _fallback(nx, ny)

    base = datetime.now() - timedelta(minutes=40)  # 실황은 매시 40분 이후 제공
    params = {
        "serviceKey": KMA_API_KEY,
        "dataType": "JSON",
        "numOfRows": 20,
        "base_date": base.strftime("%Y%m%d"),
        "base_time": base.strftime("%H00"),
        "nx": nx,
        "ny": ny,
    }
    try:
        res = requests.get(KMA_URL, params=params, timeout=5)
        items = res.json()["response"]["body"]["items"]["item"]
        vals = {i["category"]: float(i["obsrValue"]) for i in items}
        return _calc_feels_like(vals.get("T1H", 30.0), vals.get("REH", 60.0))
    except Exception:
        return _fallback(nx, ny)
