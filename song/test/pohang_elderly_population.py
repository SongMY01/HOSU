"""
경상북도 포항시_지역별 노령 인구 현황 API 호출 예제
Endpoint: https://apis.data.go.kr/5020000/areaAcctoOaPopltnSttus/getAreaAcctoOaPopltnSttus

필드 정보
─────────────────────────────────────────────────────
spm_row       : 행 번호
year          : 연도
mt            : 월
sigun         : 읍면동 (시군 단위 지역명)
se            : 구분 코드 (P=법정동, D=행정동 등)
signgu        : 시군구 (구 단위, 예: 남구·북구)
total         : 노령 인구 총합
male          : 남성 노령 인구
female        : 여성 노령 인구
ordr          : 순서
collection_dt : 수집 일시
─────────────────────────────────────────────────────
"""

import requests
import json
from urllib.parse import unquote

# ─── 설정 ────────────────────────────────────────────────────────────────────
BASE_URL = (
    "https://apis.data.go.kr/5020000/areaAcctoOaPopltnSttus"
    "/getAreaAcctoOaPopltnSttus"
)

# 포털 제공 인코딩 키
SERVICE_KEY_ENCODED = (
    "rI0FJtWisePTEU%2FVfsZuypm6Fxpse2gNDmGQfSnrf6sLsnsPeYpRo5cxFH60gMS7"
    "rWnDQVlJTkmSwF84xu57NA%3D%3D"
)
# requests 라이브러리는 params 값을 자동 인코딩하므로 디코딩 값 사용
SERVICE_KEY = unquote(SERVICE_KEY_ENCODED)

# 구분 코드 한글 매핑
SE_LABELS = {
    "P": "법정동",
    "D": "행정동",
    "G": "구",
    "S": "시군",
}


def fetch_elderly_population(
    page_no: int = 1,
    num_of_rows: int = 10,
    year: int = None,
    month: int = None,
) -> dict:
    """
    포항시 지역별 노령 인구 현황을 조회합니다.

    Parameters
    ----------
    page_no     : 페이지 번호 (기본값 1)
    num_of_rows : 한 페이지 결과 수 (기본값 10, 최대 1000)
    year        : 조회 연도 (예: 2024) — None 이면 전체
    month       : 조회 월  (예: 1)    — None 이면 전체

    Returns
    -------
    dict : API 응답 전체 (JSON)
    """
    params: dict = {
        "serviceKey": SERVICE_KEY,
        "pageNo": page_no,
        "numOfRows": num_of_rows,
        "type": "json",
    }
    if year is not None:
        params["year"] = year
    if month is not None:
        params["month"] = month

    response = requests.get(BASE_URL, params=params, timeout=10)
    response.raise_for_status()
    return response.json()


def print_result(data: dict) -> None:
    """조회 결과를 보기 좋게 출력합니다."""
    try:
        header = data["response"]["header"]
        body = data["response"]["body"]

        if header.get("resultCode") != "00":
            print(f"[API 오류] {header.get('resultMsg', '알 수 없는 오류')}")
            return

        total_count = body.get("totalCount", 0)
        items_raw = body.get("items", {})
        rows = items_raw.get("item", [])
        if isinstance(rows, dict):
            rows = [rows]

        print(f"\n{'═'*62}")
        print(f"  경상북도 포항시  지역별 노령 인구 현황")
        print(f"{'═'*62}")
        print(f"  전체 건수 : {total_count:,}건  /  현재 페이지 : {body.get('pageNo')}p"
              f"  ({len(rows)}건 표시)")
        print(f"{'─'*62}")

        for i, row in enumerate(rows, start=1):
            se_code = row.get("se", "-")
            se_label = SE_LABELS.get(se_code, se_code)
            print(
                f"  [{i:>2}]  "
                f"{row.get('year', '-')}년 {row.get('mt', '-'):>2}월  │  "
                f"시군구: {row.get('signgu', '-'):>3}  │  "
                f"지역: {row.get('sigun', '-'):<10}  │  "
                f"구분: {se_label}"
            )
            print(
                f"        총합: {int(row.get('total', 0)):>7,}명  │  "
                f"남성: {int(row.get('male', 0)):>7,}명  │  "
                f"여성: {int(row.get('female', 0)):>7,}명"
            )
            print(f"{'─'*62}")

    except (KeyError, TypeError) as e:
        print(f"\n[오류] 응답 파싱 실패: {e}")
        print("원본 응답:")
        print(json.dumps(data, ensure_ascii=False, indent=2))


def main():
    print("포항시 지역별 노령 인구 현황 조회를 시작합니다...")

    # 예시 1: 최근 데이터 5건 조회
    data = fetch_elderly_population(page_no=1, num_of_rows=5)
    print_result(data)

    # 예시 2: 연도/월 필터링 조회 (2025년 7월)
    print("\n\n[ 2025년 7월 데이터 조회 ]")
    data2 = fetch_elderly_population(page_no=1, num_of_rows=10, year=2025, month=7)
    print_result(data2)


if __name__ == "__main__":
    main()
