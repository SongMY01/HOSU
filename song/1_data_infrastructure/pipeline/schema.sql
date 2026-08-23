-- HOSU 폭염 위험도 데이터 스키마
-- 파이프라인이 write, MCP 서버가 read-only로 사용하는 계약

-- 1. 행정구역 마스터 (정적, 연 단위 갱신)
CREATE TABLE IF NOT EXISTS regions (
    region_code   TEXT PRIMARY KEY,       -- 행정표준코드 (법정동코드 10자리)
    sido          TEXT NOT NULL,          -- 시도명 (경상북도)
    sigungu       TEXT NOT NULL,          -- 시군구명 (포항시 북구)
    eupmyeondong  TEXT,                   -- 읍면동명 (NULL이면 시군구 단위 집계행)
    level         TEXT NOT NULL,          -- 'sigungu' | 'eupmyeondong'
    lat           REAL NOT NULL,          -- 중심점 위도 (WGS84)
    lon           REAL NOT NULL,          -- 중심점 경도 (WGS84)
    kma_nx        INTEGER,                -- 기상청 격자 X
    kma_ny        INTEGER                 -- 기상청 격자 Y
);

-- 2. 취약인구 지표 (정적, 연 단위 갱신)
CREATE TABLE IF NOT EXISTS vulnerability (
    region_code       TEXT PRIMARY KEY REFERENCES regions(region_code),
    total_population  INTEGER,
    elderly_65_plus   INTEGER,            -- 65세 이상 인구
    elderly_ratio     REAL,               -- 65세 이상 비율, 0.0 ~ 1.0
    elderly_75_ratio  REAL,               -- 75세 이상 비율(누적), 0.0 ~ 1.0
    elderly_85_ratio  REAL,               -- 85세 이상 비율(누적), 0.0 ~ 1.0
    base_year         INTEGER             -- 통계 기준연도
);

-- 3. 무더위쉼터 접근성 (준정적, 주 단위 갱신)
-- 쉼터 배치·접근성. 세 지표가 서로 다른 질문에 답하므로 함께 봐야 한다.
CREATE TABLE IF NOT EXISTS shelter_access (
    region_code        TEXT PRIMARY KEY REFERENCES regions(region_code),
    shelter_count      INTEGER,           -- 관내 쉼터 수(근사). 주소의 읍면동명 우선,
                                          -- 없으면 최근접 중심점 폴백 — 참고 지표용이며
                                          -- 사각지대 판정에는 쓰지 않는다
    within_400m_count  INTEGER,           -- 마을 중심점에서 도보 5분(400m) 내 쉼터 수
                                          -- 주민 집 기준이 아니라 중심점 기준임에 유의
    nearest_distance_m REAL,              -- 최근접 쉼터까지 거리(m), 행정구역 무관
    is_blind_spot      INTEGER,           -- 1이면 최근접 쉼터가 도보 15분(1.2km) 밖.
                                          -- NULL이면 해당 시군구가 쉼터 조사 대상이 아님
    updated_at         TEXT
);

-- 4. 온열질환 발생 이력 (시군구 × 연도 × 연령대 해상도)
-- 연령대가 PK에 포함돼야 한다. 원본이 (지역,연도,연령대)별 집계라 PK가 (region_code, year)
-- 뿐이면 같은 해의 다른 연령대 행이 통째로 유실된다.
-- 위험도 점수는 최근 3년만 쓰고(최근 경향 반영), 화면 표기는 전체 누적을 쓴다 —
-- 둘 다 이 한 테이블에서 질의로 파생시킨다.
CREATE TABLE IF NOT EXISTS heat_illness_history (
    region_code    TEXT REFERENCES regions(region_code),
    year           INTEGER,
    age_group      TEXT NOT NULL,         -- '10대 미만' | '10대' ... | '80대 이상'
    case_count     INTEGER,               -- 해당 연도·연령대 온열질환자 수
    death_count    INTEGER,
    PRIMARY KEY (region_code, year, age_group)
);

-- 5. 사전계산된 정적 위험도 점수 (파이프라인 산출물)
CREATE TABLE IF NOT EXISTS static_risk_scores (
    region_code        TEXT PRIMARY KEY REFERENCES regions(region_code),
    elderly_score      REAL,              -- 0~100 정규화
    shelter_score      REAL,              -- 접근성 나쁠수록 높음
    history_score      REAL,
    static_total       REAL,              -- 가중합 (실시간 기온 제외한 기저 위험도)
    computed_at        TEXT
);

-- 6. 무더위쉼터 마스터 위치 및 상세 시설 정보
CREATE TABLE IF NOT EXISTS shelters (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    sigungu        TEXT NOT NULL,          -- 시군명 (포항시, 의성군 등)
    shelter_name   TEXT NOT NULL,          -- 쉼터명 (구룡포읍행정복지센터 등)
    shelter_type   TEXT,                   -- 쉼터유형 (공공시설, 특정계층이용시설 등)
    road_address   TEXT,                   -- 도로명주소
    lot_address    TEXT,                   -- 지번주소
    lat            REAL NOT NULL,          -- 위도 (WGS84)
    lon            REAL NOT NULL,          -- 경도 (WGS84)
    area_m2        REAL,                   -- 시설면적(㎡)
    capacity       INTEGER,                -- 이용가능인원
    fans           INTEGER,                -- 선풍기 보유대수
    aircons        INTEGER,                -- 에어컨 보유대수
    night_open     TEXT,                   -- 야간운영여부 (예/아니오)
    weekend_open   TEXT,                   -- 휴일운영여부 (예/아니오)
    stay_open      TEXT                    -- 숙박가능여부 (예/아니오)
);

-- 8. 실시간/단기예보 기상 실측 데이터 (시간 단위 갱신)
CREATE TABLE IF NOT EXISTS realtime_weather (
    region_code   TEXT PRIMARY KEY REFERENCES regions(region_code),
    sigungu       TEXT NOT NULL,
    eupmyeondong  TEXT,
    grid_nx       INTEGER,
    grid_ny       INTEGER,
    announce_time TEXT,
    temperature   REAL,               -- 기온(°C)
    humidity      REAL,               -- 습도(%)
    feels_like    REAL,               -- 체감온도(°C)
    risk_tier     TEXT                -- 관심 | 주의 | 경고 | 위험
);

CREATE INDEX IF NOT EXISTS idx_regions_sigungu ON regions(sigungu);
CREATE INDEX IF NOT EXISTS idx_illness_region ON heat_illness_history(region_code);
CREATE INDEX IF NOT EXISTS idx_static_total ON static_risk_scores(static_total DESC);
CREATE INDEX IF NOT EXISTS idx_shelters_sigungu ON shelters(sigungu);
CREATE INDEX IF NOT EXISTS idx_shelters_lat_lon ON shelters(lat, lon);
CREATE INDEX IF NOT EXISTS idx_weather_nx_ny ON realtime_weather(grid_nx, grid_ny);


