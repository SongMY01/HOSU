"""
생활안전지도 - 무더위쉼터 정보조회 서비스
경상북도 전체 데이터 → CSV 파일 저장

전략: 1000건씩 페이징하며 '경상북도' 주소 필터링 → 전체 수집 후 CSV 저장
"""

import xml.etree.ElementTree as ET
from urllib.parse import urlencode
from typing import Optional, List, Dict
import urllib.request
import urllib.error
import csv
import os
import time
from datetime import datetime

# ─── 설정 ────────────────────────────────────────────────────────────────────
SERVICE_KEY  = "N0QZGM34-N0QZ-N0QZ-N0QZ-N0QZGM34EA"
BASE_URL     = "http://safemap.go.kr/openapi2/IF_0001"
BATCH_SIZE   = 1000  # 한 번에 가져올 건수

# CSV 저장 경로 (스크립트와 같은 폴더)
SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
TIMESTAMP    = datetime.now().strftime("%Y%m%d_%H%M%S")
OUTPUT_CSV   = os.path.join(SCRIPT_DIR, f"gyeongbuk_heat_shelter_{TIMESTAMP}.csv")

# CSV 컬럼 정의 (한글 헤더)
CSV_COLUMNS = [
    ("num",        "번호"),
    ("buld_sn",    "건물일련번호"),
    ("cc_nm",      "쉼터명"),
    ("cc_type",    "쉼터유형"),
    ("시군",        "시군"),
    ("rn_adres",   "도로명주소"),
    ("adres",      "지번주소"),
    ("tot_ar",     "시설면적(㎡)"),
    ("use_num",    "이용가능인원"),
    ("hv_ef",      "선풍기보유대수"),
    ("hv_ac",      "에어컨보유대수"),
    ("rest_at",    "휴식공간여부"),
    ("night_at",   "야간운영여부"),
    ("weekend_at", "휴일운영여부"),
    ("lodge_at",   "숙박가능여부"),
    ("x",          "X좌표(경도)"),
    ("y",          "Y좌표(위도)"),
]

YN_MAP = {"Y": "예", "N": "아니오", "": "-"}


# ─── API 호출 ────────────────────────────────────────────────────────────────
def fetch_page(page_no: int, num_of_rows: int, max_retry: int = 5) -> str:
    """API 호출 — 실패 시 지수 백오프로 최대 max_retry회 재시도"""
    params = {
        "serviceKey": SERVICE_KEY,
        "pageNo":     page_no,
        "numOfRows":  num_of_rows,
        "returnType": "xml",
    }
    url = f"{BASE_URL}?{urlencode(params)}"
    wait = 2  # 초기 대기 시간(초)
    for attempt in range(1, max_retry + 1):
        try:
            with urllib.request.urlopen(url, timeout=20) as resp:
                return resp.read().decode("utf-8")
        except (urllib.error.URLError, OSError) as e:
            if attempt == max_retry:
                raise
            print(f"\n  [재시도 {attempt}/{max_retry}] 오류: {e} → {wait}초 후 재시도...",
                  end="", flush=True)
            time.sleep(wait)
            wait *= 2  # 지수 백오프: 2 → 4 → 8 → 16 → 32초


def parse_page(xml_text: str):
    """(totalCount, items) 반환"""
    root  = ET.fromstring(xml_text)
    total = int(root.findtext(".//totalCount", "0"))
    items = []
    for item in root.findall(".//item"):
        row = {child.tag: (child.text or "").strip() for child in item}
        items.append(row)
    return total, items


# ─── 주소에서 시군 추출 ───────────────────────────────────────────────────────
def extract_sigungu(address: str) -> Optional[str]:
    """
    '경상북도 포항시 남구 ...' → '포항시'
    경상북도 소속이 아니면 None 반환
    """
    if "경상북도" not in address:
        return None
    parts = address.split()
    try:
        idx = parts.index("경상북도")
        city = parts[idx + 1]
        for suffix in ("시", "군"):
            if city.endswith(suffix):
                return city
        return city
    except (ValueError, IndexError):
        return None


# ─── 전체 수집 ───────────────────────────────────────────────────────────────
def collect_all_gyeongbuk() -> List[Dict]:
    """경상북도 무더위쉼터 전체 데이터를 수집합니다."""
    all_rows: List[Dict] = []
    page_no = 1

    print("경상북도 무더위쉼터 전체 데이터 수집 중", end="", flush=True)

    while True:
        xml_text     = fetch_page(page_no, BATCH_SIZE)
        total, items = parse_page(xml_text)
        total_pages  = (total + BATCH_SIZE - 1) // BATCH_SIZE

        for item in items:
            addr = item.get("rn_adres", "") or item.get("adres", "")
            city = extract_sigungu(addr)
            if city is None:
                continue
            item["시군"] = city
            # Y/N 필드 한글 변환
            for key in ("rest_at", "night_at", "weekend_at", "lodge_at"):
                item[key] = YN_MAP.get(item.get(key, ""), item.get(key, "-"))
            all_rows.append(item)

        print(f".", end="", flush=True)

        if page_no >= total_pages:
            break
        page_no += 1

    print(f" 완료!\n")
    print(f"  → 전국 전체: {total:,}건")
    print(f"  → 경상북도 수집: {len(all_rows):,}건")
    return all_rows


# ─── CSV 저장 ────────────────────────────────────────────────────────────────
def save_to_csv(rows: List[Dict], filepath: str) -> None:
    """수집된 데이터를 CSV 파일로 저장합니다."""
    field_keys   = [col[0] for col in CSV_COLUMNS]
    field_labels = [col[1] for col in CSV_COLUMNS]

    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=field_keys, extrasaction="ignore")
        # 한글 헤더 행 직접 작성
        f.write(",".join(field_labels) + "\n")
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in field_keys})

    print(f"\n  저장 완료 → {filepath}")
    print(f"  총 {len(rows):,}행 / {len(field_labels)}개 컬럼")


# ─── 시군별 요약 출력 ────────────────────────────────────────────────────────
def print_summary(rows: List[Dict]) -> None:
    from collections import Counter
    counts = Counter(row.get("시군", "기타") for row in rows)
    print(f"\n{'─'*40}")
    print(f"  시군별 데이터 건수 (총 {len(counts)}개 시군)")
    print(f"{'─'*40}")
    for city, cnt in sorted(counts.items()):
        print(f"  {city:<8} : {cnt:>4}건")
    print(f"{'─'*40}")


# ─── 진입점 ──────────────────────────────────────────────────────────────────
def main():
    rows = collect_all_gyeongbuk()
    print_summary(rows)
    save_to_csv(rows, OUTPUT_CSV)


if __name__ == "__main__":
    main()
