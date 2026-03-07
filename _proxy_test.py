from curl_cffi import requests
import uuid, time, random, json, re

PROXY = "http://lniuniah:9x34w57nd07r@31.59.20.176:6754"

s = requests.Session(impersonate="chrome", proxies={"http": PROXY, "https": PROXY})
r = s.get(
    "https://www.justwatch.com/us",
    timeout=15,
    headers={"Accept-Language": "en-US,en;q=0.9"},
)
print("Homepage:", r.status_code)
print("Cookies:", dict(s.cookies))

# Look for device ID hints in page source
src = r.text
for pattern in [
    r'"deviceId"\s*:\s*"([^"]+)"',
    r'device.id["\s:=]+([a-f0-9-]{30,})',
    r'deviceId["\s:=]+([a-f0-9-]{30,})',
]:
    m = re.search(pattern, src)
    if m:
        print(f"Found deviceId in page: {m.group(1)}")

# Try the GraphQL with no device-id header at all
time.sleep(0.8)
device_id = str(uuid.uuid4())
QUERY = """query GetProviderTitles($country: Country!, $language: Language!, $first: Int!, $after: String, $packageIds: [String!]!, $objectTypes: [ObjectType!], $sortBy: PopularTitlesSorting!) {
  popularTitles(country: $country filter: {packages: $packageIds, objectTypes: $objectTypes} first: $first after: $after sortBy: $sortBy sortRandomSeed: 0) {
    edges { node { objectType content(country: $country, language: $language) { title } } }
  }
}"""

for test_name, extra_hdrs in [
    ("no device-id", {}),
    ("random uuid", {"device-id": device_id}),
    ("short id", {"device-id": "abc123"}),
    ("cookie device_id", {"device-id": s.cookies.get("jw_device_id", device_id)}),
]:
    r2 = s.post(
        "https://apis.justwatch.com/graphql",
        json={
            "operationName": "GetProviderTitles",
            "query": QUERY,
            "variables": {
                "country": "US",
                "language": "en",
                "first": 2,
                "after": None,
                "packageIds": ["8"],
                "objectTypes": ["MOVIE"],
                "sortBy": "POPULAR",
            },
        },
        headers={
            "Origin": "https://www.justwatch.com",
            "Referer": "https://www.justwatch.com/",
            "apollographql-client-name": "web",
            "apollographql-client-version": "3.8.2-web",
            "app-version": "3.8.2-web",
            **extra_hdrs,
        },
        timeout=15,
    )
    if r2.status_code == 200:
        edges = r2.json().get("data", {}).get("popularTitles", {}).get("edges", [])
        print(f"[{test_name}] OK — {[e['node']['content']['title'] for e in edges]}")
        break
    else:
        print(f"[{test_name}] {r2.status_code}: {r2.text[:80]}")
    time.sleep(0.5)
