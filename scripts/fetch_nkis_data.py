import requests, time, csv, os
from xml.etree import ElementTree as ET
from datetime import datetime

API_KEY = os.environ.get("NKIS_API_KEY", "AC359DA021C027C55E42")
BASE = "https://nkis.re.kr/nkisApi/search/ReportList.do"

KEYWORDS = {
    "지역산업": "regional_industry",
    "지역발전": "regional_development",
    "도시재생": "urban_regeneration",
    "인구감소": "population_decline",
    "산업단지": "industrial_complex",
    "울산": "ulsan_direct",
}

results = []

for kw, tag in KEYWORDS.items():
    print(f"[{kw}] 요청중...", flush=True)
    try:
        r = requests.get(BASE, params={
            "serviceKey": API_KEY,
            "pageNo": 1, "rowCnt": 100,
            "otpHanNm": kw,
            "pblYrBegin": 2000, "pblYrEnd": 2026,
        }, timeout=20)
        root = ET.fromstring(r.text)
        items = root.findall(".//result")
        yr = {}
        for item in items:
            y = item.findtext("PBL_YY","").strip()
            if y.isdigit():
                yr[y] = yr.get(y,0) + 1
        print(f"[{kw}] {len(items)}건 ✅", flush=True)
        for y in sorted(yr):
            results.append({"keyword":kw,"tag":tag,"year":y,"count":yr[y]})
    except Exception as e:
        print(f"[{kw}] ERROR: {e}", flush=True)
    time.sleep(3)

out = os.path.join(os.path.dirname(__file__), "../data/nkis_policy_timeseries.csv")
os.makedirs(os.path.dirname(out), exist_ok=True)
with open(out,"w",newline="",encoding="utf-8") as f:
    w = csv.DictWriter(f,fieldnames=["keyword","tag","year","count"])
    w.writeheader()
    w.writerows(results)

print(f"\n저장완료: {out}")
print(f"수집일시: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
