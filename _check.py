"""Query JustWatch for all available US streaming packages to find missing platforms."""

from curl_cffi import requests
import os
from dotenv import load_dotenv

load_dotenv()

PROXY = os.getenv("SCRAPER_PROXY_URL")
s = requests.Session(
    impersonate="chrome", proxies={"http": PROXY, "https": PROXY} if PROXY else {}
)

QUERY = """
query GetPackages($country: Country!, $platform: Platform!) {
  packages(country: $country, platform: $platform) {
    id packageId clearName technicalName
  }
}"""

r = s.post(
    "https://apis.justwatch.com/graphql",
    json={
        "operationName": "GetPackages",
        "query": QUERY,
        "variables": {"country": "US", "platform": "WEB"},
    },
    headers={
        "Origin": "https://www.justwatch.com",
        "Referer": "https://www.justwatch.com/",
        "apollographql-client-name": "web",
        "apollographql-client-version": "3.8.2-web",
        "app-version": "3.8.2-web",
    },
    timeout=15,
)

print(f"Status: {r.status_code}")
if r.status_code == 200:
    pkgs = r.json().get("data", {}).get("packages", [])
    for p in sorted(pkgs, key=lambda x: x["clearName"].lower()):
        print(
            f"  packageId={p['packageId']:>5}  {p['clearName']:<35}  tech={p['technicalName']}"
        )
else:
    print(r.text[:400])

print("=== Rookie in US ===")
for r in conn.execute(
    "SELECT title, platform, region, content_type, ranking_position FROM titles WHERE title LIKE '%Rookie%' AND region='US'"
):
    print(r)

print("\n=== Total US titles ===")
print(conn.execute("SELECT COUNT(*) FROM titles WHERE region='US'").fetchone()[0])

print("\n=== Per-platform counts (US) ===")
for r in conn.execute(
    "SELECT platform, content_type, COUNT(*) c FROM titles WHERE region='US' GROUP BY platform, content_type ORDER BY platform"
):
    print(r)

print("\n=== Sample Disney+/US TV titles ===")
for r in conn.execute(
    "SELECT title, ranking_position FROM titles WHERE region='US' AND platform='disney_plus' AND content_type='tv' ORDER BY ranking_position LIMIT 20"
):
    print(r)
conn.close()
