import sqlite3

# 이 서비스의 대상 범위는 경상북도뿐이다. 행정구역코드는 emd_code·sigungu_code 모두
# 앞 2자리가 시도코드라, 47로 시작하는지만 보면 둘 다 판정된다(대구 27은 제외됨).
TARGET_SIDO_CODE = "47"
TARGET_SIDO_NAME = "경상북도"


def is_target_region(code: str) -> bool:
    """emd_code 또는 sigungu_code가 대상 지역(경북)인지."""
    return str(code).startswith(TARGET_SIDO_CODE)


def require_target_region(code: str) -> None:
    """대상 범위 밖이면 에러. 조회 결과 없음(빈 값)과 범위 밖을 구분하기 위함."""
    if not is_target_region(code):
        raise ValueError(
            f"'{code}'은(는) 대상 범위 밖입니다. 이 서비스는 {TARGET_SIDO_NAME}"
            f"({TARGET_SIDO_CODE}로 시작하는 행정구역코드)만 다룹니다."
        )


# 기상청 API허브 특보 API는 emd_code/sigungu_code(법정동코드, "47" 접두어)와 전혀 다른
# 코드 체계(REG_ID, 예: "L1072700"=안동시)를 쓴다. 실호출로 확인함 — 경북 산하 REG_ID는
# 전부 "L107"로 시작하고(L1070000=경상북도 자체 포함), 대구는 별도 접두어(L114)로 완전히
# 분리돼 있어 47/27 시도코드 때와 같은 패턴으로 안전하게 걸러진다.
TARGET_ALERT_ZONE_PREFIX = "L107"


def is_target_alert_zone(alert_zone_code: str) -> bool:
    """REG_ID/REG_UP(기상특보 구역코드)가 대상 지역(경북)인지. is_target_region과는 다른 코드 체계."""
    return str(alert_zone_code).startswith(TARGET_ALERT_ZONE_PREFIX)


SCHEMA = """
-- alert_zone_code = 기상청 API허브 특보구역코드(REG_ID, 예: "L1072700"=안동시). grid_nx/grid_ny
-- (5km 격자, 초단기실황용)와는 완전히 다른 좌표계라 별도 컬럼으로 둔다 — 격자로 근사 매핑하지
-- 않는다. (data.go.kr의 지점코드(stnId) 기반 특보 API는 구조 불일치로 폐기, 기상청 API허브의
-- REG_ID 기반 API로 교체함 — WRN/LVL이 코드로 구조화돼 있어 텍스트 파싱이 필요 없음)
CREATE TABLE IF NOT EXISTS ADMIN_REGION (
    emd_code TEXT PRIMARY KEY,
    sido_name TEXT,
    sigungu_name TEXT,
    emd_name TEXT,
    grid_nx INTEGER,
    grid_ny INTEGER,
    alert_zone_code TEXT,
    center_lat REAL,
    center_lon REAL
);

CREATE TABLE IF NOT EXISTS WEATHER_ALERT (
    grid_nx INTEGER,
    grid_ny INTEGER,
    announce_time TEXT,
    alert_type TEXT,
    temperature REAL,
    feels_like REAL,
    humidity REAL,
    PRIMARY KEY (grid_nx, grid_ny, announce_time)
);

-- 기상특보(폭염경보 등)는 alert_zone_code(지점코드) 기준이라 WEATHER_ALERT(격자 기준)와
-- 같은 테이블에 못 넣는다 — 한 PK에 두 좌표계를 섞으면 HEAT_ILLNESS에서 겪었던 것과 같은
-- NULL-in-PK 문제가 재발한다. title은 "OO시 폭염경보 발표"류 원문 그대로 보존하고,
-- alert_type은 그걸 파싱해서 채우는 후속 작업 — 지금은 비워둔다.
CREATE TABLE IF NOT EXISTS WEATHER_WARNING (
    alert_zone_code TEXT NOT NULL,
    announce_time TEXT NOT NULL,
    tm_seq INTEGER NOT NULL,
    title TEXT,
    alert_type TEXT,
    PRIMARY KEY (alert_zone_code, announce_time, tm_seq)
);

-- age_group이 PK에 포함돼야 한다. 온열질환 데이터는 (지역, 날짜, 연령대)별 집계라
-- 같은 시군구·같은 날짜에 여러 연령대 행이 들어온다. PK가 (sigungu_code, occur_date)뿐이면
-- 첫 연령대만 적재되고 나머지는 IntegrityError로 통째로 실패한다.
-- NOT NULL도 필요하다: SQLite는 INTEGER PRIMARY KEY가 아닌 PK 컬럼에 NULL을 허용해서,
-- age_group이 비면 중복 행이 조용히 쌓인다.
CREATE TABLE IF NOT EXISTS HEAT_ILLNESS (
    sigungu_code TEXT NOT NULL,
    occur_date TEXT NOT NULL,
    age_group TEXT NOT NULL,
    patient_count INTEGER,
    is_death INTEGER,
    PRIMARY KEY (sigungu_code, occur_date, age_group)
);

CREATE TABLE IF NOT EXISTS SAFETY_TARGET (
    target_id TEXT PRIMARY KEY,
    emd_code TEXT REFERENCES ADMIN_REGION(emd_code),
    target_count INTEGER
);

CREATE TABLE IF NOT EXISTS HEAT_SHELTER (
    shelter_id TEXT PRIMARY KEY,
    emd_code TEXT REFERENCES ADMIN_REGION(emd_code),
    name TEXT,
    lat REAL,
    lon REAL,
    capacity INTEGER,
    has_aircon INTEGER
);

-- address는 원래 ER 설계엔 없던 컬럼. 소스 API(한국사회보장정보원)가 emd_code나 좌표 없이
-- 주소 텍스트만 주기 때문에, 지오코딩(JUSO_API_KEY 대기중) 전까지 원본 주소를 보관해둘
-- 곳이 필요해서 추가함 — 지오코딩 붙으면 emd_code/lat/lon을 채우고 이 컬럼은 그대로 원본
-- 감사(audit) 기록으로 남긴다.
CREATE TABLE IF NOT EXISTS WELFARE_FACILITY (
    facility_id TEXT PRIMARY KEY,
    emd_code TEXT REFERENCES ADMIN_REGION(emd_code),
    name TEXT,
    facility_type TEXT,
    address TEXT,
    lat REAL,
    lon REAL
);

CREATE TABLE IF NOT EXISTS EMERGENCY_HOSPITAL (
    hospital_id TEXT PRIMARY KEY,
    emd_code TEXT REFERENCES ADMIN_REGION(emd_code),
    name TEXT,
    lat REAL,
    lon REAL,
    available_beds INTEGER
);

CREATE TABLE IF NOT EXISTS RISK_SCORE (
    emd_code TEXT REFERENCES ADMIN_REGION(emd_code),
    score_date TEXT,
    exposure_score REAL,
    sensitivity_score REAL,
    access_score REAL,
    total_score REAL,
    priority_tier TEXT,
    nearest_shelter_id TEXT REFERENCES HEAT_SHELTER(shelter_id),
    PRIMARY KEY (emd_code, score_date)
);
"""


def get_conn(path: str = "hosu_heat.db") -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    return conn
