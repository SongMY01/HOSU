"""읍면동 세분화 검증용 미니 프로토타입.

경북 302개 격자 전체를 실호출로 채우고, 카테고리별(기온/온열질환) 레이어 + 종합 위험도
레이어를 Leaflet 지도 한 장(prototype_map.html)으로 렌더링한다. 실제 API 응답으로
"카테고리별로 되는지" 확인하는 게 목적이라, 데이터 없는 항목(복지시설 좌표·쉼터·독거노인)은
아예 빼고 실데이터가 있는 두 축(기온, 온열질환)만 다룬다.

실행: python build_prototype.py  (약 20~30초, KMA API 302회 호출)
"""

import json
from datetime import datetime

from dotenv import load_dotenv

from pipeline.db import get_conn
from pipeline.scoring import TIER_COLOR, feels_like_c, risk_tier
from pipeline.sources import emd_centroid, heat_illness, weather

OUTPUT_PATH = "prototype_map.html"


def build_points(conn) -> list[dict]:
    """읍면동(leaf) 단위 포인트 — 기온·습도·체감온도·등급 + 시군구 온열질환 누적(상속)."""
    illness_by_sgg = dict(
        conn.execute("SELECT sigungu_code, SUM(patient_count) FROM HEAT_ILLNESS GROUP BY sigungu_code")
    )

    rows = conn.execute(
        """
        SELECT a.emd_code, a.sigungu_name, a.emd_name, a.center_lat, a.center_lon,
               a.grid_nx, a.grid_ny, w.temperature, w.humidity, w.announce_time
        FROM ADMIN_REGION a
        LEFT JOIN WEATHER_ALERT w
          ON w.grid_nx = a.grid_nx AND w.grid_ny = a.grid_ny
         AND w.announce_time = (
             SELECT MAX(w2.announce_time) FROM WEATHER_ALERT w2
             WHERE w2.grid_nx = a.grid_nx AND w2.grid_ny = a.grid_ny
         )
        WHERE a.emd_name IS NOT NULL
        """
    ).fetchall()

    points = []
    for emd_code, sgg_name, emd_name, lat, lon, nx, ny, temp, humidity, announce_time in rows:
        if temp is None or humidity is None:
            continue  # 그 격자 호출이 실패했거나(§6-1 failed) 결측 센티널로 걸러진 경우
        fl = round(feels_like_c(temp, humidity), 1)
        sigungu_code = emd_code[:5] + "00000"
        points.append(
            {
                "emd_code": emd_code,
                "sigungu_name": sgg_name,
                "emd_name": emd_name,
                "lat": lat,
                "lon": lon,
                "temperature": temp,
                "humidity": humidity,
                "feels_like": fl,
                "tier": risk_tier(fl),
                "announce_time": announce_time,
                "illness_total": illness_by_sgg.get(sigungu_code),  # 시군구 누적, 상속값
            }
        )
    return points


def build_illness_points(conn) -> list[dict]:
    """온열질환 전용 레이어 — 시군구 대표좌표 1점당 1마커(읍면동에 뿌리면 없는 정밀도를
    있는 것처럼 보이게 됨, SPEC §7)."""
    illness_by_sgg = dict(
        conn.execute("SELECT sigungu_code, SUM(patient_count) FROM HEAT_ILLNESS GROUP BY sigungu_code")
    )
    parents = {r["emd_code"]: r for r in emd_centroid.read_rows() if r["sigungu_name"] and r["emd_name"] is None}

    out = []
    for sigungu_code, total in illness_by_sgg.items():
        parent = parents.get(sigungu_code)
        if parent is None:
            continue
        out.append(
            {
                "sigungu_name": parent["sigungu_name"],
                "lat": parent["center_lat"],
                "lon": parent["center_lon"],
                "total": total,
            }
        )
    return out


def render_html(points: list[dict], illness_points: list[dict], stats: dict) -> str:
    data = {
        "points": points,
        "illness_points": illness_points,
        "tierColor": TIER_COLOR,
        "generatedAt": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "stats": stats,
    }
    return _TEMPLATE.replace("__DATA_JSON__", json.dumps(data, ensure_ascii=False))


_TEMPLATE = r"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<title>경북 읍면동 폭염대응 프로토타입</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
      integrity="sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=" crossorigin="">
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"
        integrity="sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=" crossorigin=""></script>
<style>
  html, body { margin:0; height:100%; font-family:-apple-system,"Malgun Gothic",sans-serif; }
  #app { display:flex; height:100%; }
  #sidebar { width:340px; overflow-y:auto; border-right:1px solid #e5e7eb; padding:16px; box-sizing:border-box; }
  #map { flex:1; }
  h1 { font-size:18px; margin:0 0 4px; }
  .meta { color:#6b7280; font-size:12px; margin-bottom:12px; }
  .layer-toggle label { display:block; font-size:13px; margin:4px 0; cursor:pointer; }
  .rank-item { border:1px solid #e5e7eb; border-radius:8px; padding:8px 10px; margin:6px 0; cursor:pointer; font-size:13px; }
  .rank-item:hover { background:#f9fafb; }
  .tier-badge { display:inline-block; padding:2px 8px; border-radius:999px; color:#fff; font-size:11px; font-weight:600; }
  .caveats { font-size:11px; color:#92400e; background:#fffbeb; border:1px solid #fde68a; border-radius:8px; padding:8px 10px; margin-top:14px; line-height:1.5; }
  .legend { position:absolute; bottom:20px; right:20px; background:#fff; padding:8px 12px; border-radius:8px; box-shadow:0 1px 4px rgba(0,0,0,.2); font-size:12px; z-index:1000; }
  .legend span { display:inline-block; width:10px; height:10px; border-radius:50%; margin-right:4px; }
</style>
</head>
<body>
<div id="app">
  <div id="sidebar">
    <h1>경북 읍면동 폭염대응 프로토타입</h1>
    <div class="meta" id="meta"></div>

    <div class="layer-toggle">
      <label><input type="checkbox" id="toggle-combined" checked> 종합 위험도 (읍면동, <span id="n-combined"></span>)</label>
      <label><input type="checkbox" id="toggle-temp"> 기온만 (읍면동)</label>
      <label><input type="checkbox" id="toggle-illness"> 온열질환 누적 (시군구, <span id="n-illness"></span>)</label>
    </div>

    <div id="rank-list"></div>

    <div class="caveats">
      ⚠ 온열질환은 시군구 단위 누적 통계(2011~2025)라 같은 군의 모든 읍면동이 같은 값을
      상속받는다 — 실제 읍면동별 차이가 아니다.<br>
      ⚠ 기온·체감온도는 기상청 5km 격자 기준. 인접 읍면동이 같은 격자를 쓰면 값이 같다.<br>
      ⚠ 체감온도는 생활기상지수 API 미연결로 자체 계산(기온+습도 공식)한 근사치다.
    </div>
  </div>
  <div id="map"></div>
</div>
<div class="legend">
  <div><span style="background:#dc2626"></span>위험(체감 35℃↑)</div>
  <div><span style="background:#f59e0b"></span>주의(체감 33℃↑)</div>
  <div><span style="background:#16a34a"></span>양호</div>
</div>
<script>
const DATA = __DATA_JSON__;

document.getElementById('meta').textContent =
  `생성 ${DATA.generatedAt} · 읍면동 ${DATA.points.length}개 · 온열질환 시군구 ${DATA.illness_points.length}개`;
document.getElementById('n-combined').textContent = DATA.points.length;
document.getElementById('n-illness').textContent = DATA.illness_points.length;

const map = L.map('map').setView([36.4, 128.8], 9);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
  attribution: '&copy; OpenStreetMap contributors'
}).addTo(map);

function popupCombined(p) {
  const illness = p.illness_total == null
    ? '데이터 없음'
    : `${p.illness_total}건 (${p.sigungu_name} 전체 누적 · 상속값)`;
  return `<b>${p.sigungu_name} ${p.emd_name}</b><br>
    기온 ${p.temperature}℃ · 습도 ${p.humidity}%<br>
    체감온도 <b>${p.feels_like}℃</b> — <span class="tier-badge" style="background:${DATA.tierColor[p.tier]}">${p.tier}</span><br>
    온열질환 이력: ${illness}`;
}

const combinedLayer = L.layerGroup(DATA.points.map(p =>
  L.circleMarker([p.lat, p.lon], {
    radius: 6, color: DATA.tierColor[p.tier], fillColor: DATA.tierColor[p.tier], fillOpacity: 0.75, weight: 1
  }).bindPopup(popupCombined(p))
));

const tempLayer = L.layerGroup(DATA.points.map(p =>
  L.circleMarker([p.lat, p.lon], {
    radius: 5, color: '#2563eb', fillColor: '#2563eb', fillOpacity: 0.6, weight: 1
  }).bindPopup(`<b>${p.sigungu_name} ${p.emd_name}</b><br>기온 ${p.temperature}℃ · 습도 ${p.humidity}%`)
));

const illnessLayer = L.layerGroup(DATA.illness_points.map(p =>
  L.circleMarker([p.lat, p.lon], {
    radius: Math.min(6 + p.total / 8, 26), color: '#7c3aed', fillColor: '#7c3aed', fillOpacity: 0.35, weight: 1
  }).bindPopup(`<b>${p.sigungu_name}</b><br>온열질환 누적 ${p.total}건 (2011~2025, 시군구 단위)`)
));

combinedLayer.addTo(map);

document.getElementById('toggle-combined').addEventListener('change', e =>
  e.target.checked ? combinedLayer.addTo(map) : map.removeLayer(combinedLayer));
document.getElementById('toggle-temp').addEventListener('change', e =>
  e.target.checked ? tempLayer.addTo(map) : map.removeLayer(tempLayer));
document.getElementById('toggle-illness').addEventListener('change', e =>
  e.target.checked ? illnessLayer.addTo(map) : map.removeLayer(illnessLayer));

const rankList = document.getElementById('rank-list');
const ranked = [...DATA.points].sort((a, b) => b.feels_like - a.feels_like).slice(0, 15);
ranked.forEach((p, i) => {
  const el = document.createElement('div');
  el.className = 'rank-item';
  el.innerHTML = `${i + 1}. <b>${p.sigungu_name} ${p.emd_name}</b>
    <span class="tier-badge" style="background:${DATA.tierColor[p.tier]}">${p.feels_like}℃</span>`;
  el.onclick = () => { map.flyTo([p.lat, p.lon], 12); };
  rankList.appendChild(el);
});
</script>
</body>
</html>
"""


def main():
    load_dotenv()
    conn = get_conn()

    n_regions = emd_centroid.load_all(conn)
    print(f"[1/3] ADMIN_REGION: 경북 읍면동 {n_regions}개 적재")

    weather_result = weather.refresh_all(conn)
    print(
        f"[2/3] 기상 실황: 격자 {weather_result['grids']}개 중 "
        f"캐시 {weather_result['cached']} · 신규 {weather_result['loaded']} · 실패 {weather_result['failed']}"
    )
    for err in weather_result["errors"][:5]:
        print("       실패:", err)

    illness_result = heat_illness.load(conn)
    print(
        f"[3/3] 온열질환: {illness_result['loaded']}행 적재, "
        f"시군구 미기재로 제외 {illness_result['skipped_no_sigungu']}건"
    )

    points = build_points(conn)
    illness_points = build_illness_points(conn)
    html = render_html(points, illness_points, stats=weather_result)

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"\n완료 -> {OUTPUT_PATH} (읍면동 포인트 {len(points)}개, 온열질환 시군구 {len(illness_points)}개)")
    print("브라우저에서 그냥 열면 됨 — 서버 필요 없음.")


if __name__ == "__main__":
    main()
