"""Self-check for pipeline/db.py schema invariants. Run: python -m pipeline.test_db"""

import sqlite3

from pipeline.db import get_conn, is_target_alert_zone

SGG = "47170"  # 경북 안동시


def _insert_illness(conn, age_group, occur_date="2026-08-21", patient_count=3):
    conn.execute(
        "INSERT INTO HEAT_ILLNESS (sigungu_code, occur_date, age_group, patient_count, is_death) "
        "VALUES (?, ?, ?, ?, 0)",
        (SGG, occur_date, age_group, patient_count),
    )


def test_same_day_multiple_age_groups_all_persist():
    """온열질환은 (지역, 날짜, 연령대)별 집계다. 같은 날 여러 연령대가 다 들어가야 한다."""
    conn = get_conn(":memory:")

    for age_group in ("60대", "70대", "80대이상"):
        _insert_illness(conn, age_group)
    conn.commit()

    rows = conn.execute(
        "SELECT age_group FROM HEAT_ILLNESS WHERE sigungu_code = ? AND occur_date = ? "
        "ORDER BY age_group",
        (SGG, "2026-08-21"),
    ).fetchall()
    assert [r[0] for r in rows] == ["60대", "70대", "80대이상"], rows


def test_true_duplicate_still_rejected():
    """PK가 여전히 제 역할을 해야 한다 — 같은 연령대 중복은 막혀야 함."""
    conn = get_conn(":memory:")
    _insert_illness(conn, "70대")

    try:
        _insert_illness(conn, "70대")
    except sqlite3.IntegrityError:
        pass
    else:
        raise AssertionError("동일 (지역, 날짜, 연령대) 중복이 통과했다 — PK가 무력화됨")


def test_null_age_group_rejected():
    """SQLite는 non-INTEGER PK에 NULL을 허용하므로 NOT NULL이 없으면 중복이 조용히 쌓인다."""
    conn = get_conn(":memory:")

    try:
        _insert_illness(conn, None)
    except sqlite3.IntegrityError:
        pass
    else:
        raise AssertionError("age_group=NULL이 통과했다 — NOT NULL 제약이 빠짐")


def test_weather_alert_and_warning_use_independent_coordinate_systems():
    """WEATHER_ALERT(격자)와 WEATHER_WARNING(지점코드)은 같은 announce_time이라도
    서로 다른 PK 공간이라 섞이거나 충돌하지 않아야 한다."""
    conn = get_conn(":memory:")
    conn.execute(
        "INSERT INTO WEATHER_ALERT (grid_nx, grid_ny, announce_time, temperature) "
        "VALUES (91, 106, '2026-08-22T21:00', 23.6)"
    )
    # 같은 시각, 안동 지점코드(예시)로 특보 두 건(발표번호가 다름) — 둘 다 들어가야 함
    conn.execute(
        "INSERT INTO WEATHER_WARNING (alert_zone_code, announce_time, tm_seq, title) "
        "VALUES ('136', '2026-08-22T21:00', 41, '경북 안동시 폭염경보 발표')"
    )
    conn.execute(
        "INSERT INTO WEATHER_WARNING (alert_zone_code, announce_time, tm_seq, title) "
        "VALUES ('136', '2026-08-22T21:00', 42, '경북 안동시 호우주의보 발표')"
    )
    conn.commit()

    alert_count = conn.execute("SELECT COUNT(*) FROM WEATHER_ALERT").fetchone()[0]
    warning_count = conn.execute("SELECT COUNT(*) FROM WEATHER_WARNING").fetchone()[0]
    assert alert_count == 1 and warning_count == 2, (alert_count, warning_count)


def test_weather_warning_rejects_true_duplicate():
    conn = get_conn(":memory:")
    conn.execute(
        "INSERT INTO WEATHER_WARNING (alert_zone_code, announce_time, tm_seq, title) "
        "VALUES ('136', '2026-08-22T21:00', 41, '경북 안동시 폭염경보 발표')"
    )
    try:
        conn.execute(
            "INSERT INTO WEATHER_WARNING (alert_zone_code, announce_time, tm_seq, title) "
            "VALUES ('136', '2026-08-22T21:00', 41, '중복 발표')"
        )
    except sqlite3.IntegrityError:
        pass
    else:
        raise AssertionError("동일 (지점코드, 발표시각, 발표번호) 중복이 통과했다")


def test_is_target_alert_zone_matches_live_verified_codes():
    """2026-08-22 기상청 API허브 실호출로 확인한 실제 REG_ID들 — 경북 산하는 L107, 대구(L114)는 별도."""
    gyeongbuk = ["L1070000", "L1072600", "L1072700", "L1072800", "L1072900", "L1073000", "L1073100"]
    others = ["L1140000", "L1140200", "L1080000", "L1030000", "S1230000"]

    assert all(is_target_alert_zone(c) for c in gyeongbuk)
    assert not any(is_target_alert_zone(c) for c in others)


if __name__ == "__main__":
    test_same_day_multiple_age_groups_all_persist()
    test_true_duplicate_still_rejected()
    test_null_age_group_rejected()
    test_weather_alert_and_warning_use_independent_coordinate_systems()
    test_weather_warning_rejects_true_duplicate()
    test_is_target_alert_zone_matches_live_verified_codes()
    print("OK: db.py schema self-check passed")
