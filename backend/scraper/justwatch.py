# backend/scraper/justwatch.py
"""
JustWatch GraphQL client.
Responsible for building requests, sending them, and parsing raw responses
into a list of flat title dicts. No database interaction here.
"""

import logging
import random
import re
import time
from typing import Optional

# curl_cffi impersonates a real Chrome TLS fingerprint, which is required to
# pass Cloudflare's bot detection on JustWatch.  Fall back to plain requests
# only if curl_cffi is not installed (it should always be in requirements).
try:
    from curl_cffi import requests

    _CURL_CFFI = True
except ImportError:
    import requests  # type: ignore

    _CURL_CFFI = False

from fake_useragent import UserAgent

log = logging.getLogger("Scraper")

# ── Platform config ───────────────────────────────────────────────────────────

# technicalName substrings — used to confirm a FLATRATE offer is on the right
# platform (belt-and-suspenders check alongside the package ID filter).
PLATFORM_KEYWORDS = {
    "netflix": ["netflix"],
    "disney_plus": ["disney"],
    "hbo_max": ["max", "hbo", "amazonhbomax"],
    "apple_tv": ["appletv"],
    "prime_video": ["amazonprime", "amazonprimevideowithads"],
    "hulu": ["hulu"],
    "peacock": ["peacocktv", "peacocktvpremium"],
    "paramount_plus": ["paramountplusessential", "paramountpluspremium"],
}

# JustWatch package IDs (stable across regions).
# Used to filter popularTitles by provider, returning the full catalog.
PLATFORM_PACKAGE_IDS = {
    "netflix": ["8"],
    "disney_plus": ["337"],
    "hbo_max": ["384"],  # Max (formerly HBO Max)
    "apple_tv": ["350"],
    "prime_video": ["9"],  # Amazon Prime Video
    "hulu": ["15"],  # Hulu (US)
    "peacock": ["386", "387"],  # Peacock Premium / Premium Plus (US)
    "paramount_plus": ["2616", "2303"],  # Paramount+ Essential / Premium (US)
}

PLATFORMS_ENABLED = {
    "netflix": True,
    "disney_plus": True,
    "hbo_max": True,
    "apple_tv": True,
    "prime_video": True,
    "hulu": True,
    "peacock": True,
    "paramount_plus": True,
}

# ── Session initialisation ───────────────────────────────────────────────────

# JustWatch app version embedded in every request (keeps us looking like the
# official web app rather than a raw API client).
_APP_VERSION = "3.8.2-web"
_APOLLO_CLIENT = "web"


def make_session(proxy: Optional[str] = None) -> requests.Session:
    """
    Create a HTTP session configured to pass Cloudflare bot detection.

    Uses curl_cffi with Chrome TLS impersonation when available, which spoofs
    the JA3/JA4 fingerprint that Cloudflare and JustWatch check.

    Args:
        proxy: Optional HTTP/HTTPS/SOCKS5 proxy URL, e.g.:
               "http://user:pass@host:port"
               "socks5://user:pass@host:port"
               Set via SCRAPER_PROXY_URL env var for residential proxies,
               which bypass IP-level Cloudflare blocks.
    """
    if _CURL_CFFI:
        kwargs: dict = {"impersonate": "chrome"}
        if proxy:
            kwargs["proxies"] = {"http": proxy, "https": proxy}
        return requests.Session(**kwargs)
    else:
        s = requests.Session()  # type: ignore
        if proxy:
            s.proxies = {"http": proxy, "https": proxy}
        return s


def _base_headers(ua: str) -> dict:
    """Headers that mimic a real browser visiting JustWatch."""
    return {
        "User-Agent": ua,
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Content-Type": "application/json",
        "Origin": "https://www.justwatch.com",
        "Referer": "https://www.justwatch.com/",
        # Apollo Gateway client identification — required for routing
        "apollographql-client-name": _APOLLO_CLIENT,
        "apollographql-client-version": _APP_VERSION,
        "app-version": _APP_VERSION,
        # Sec-Fetch headers sent by every real browser
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-site",
    }


def warm_session(session: requests.Session) -> None:
    """
    Visit the JustWatch homepage to pick up session cookies.
    Silently ignored on failure so a network hiccup never aborts the whole scrape.
    """
    try:
        session.get(
            "https://www.justwatch.com/us",
            headers={
                "User-Agent": get_ua(),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
            },
            timeout=12,
        )
        time.sleep(random.uniform(0.5, 1.0))
    except Exception as exc:
        log.debug(f"Session warm-up skipped: {exc}")


GRAPHQL_URL = "https://apis.justwatch.com/graphql"
# Supported values accepted by JustWatch's popularTitles sortBy argument.
# POPULAR  — by global popularity score (best for trending/catalog).
# ALPHABETICAL — A-Z title order; exposes regional long-tail content that
#                POPULAR ranking buries past the pagination horizon.
SORTABLE_BY = ["POPULAR", "ALPHABETICAL"]

GRAPHQL_QUERY = """
query GetProviderTitles(
  $country: Country!, $language: Language!,
  $first: Int!, $after: String,
  $packageIds: [String!]!,
  $objectTypes: [ObjectType!],
  $sortBy: PopularTitlesSorting!
) {
  popularTitles(
    country: $country
    filter: { packages: $packageIds, objectTypes: $objectTypes }
    first: $first
    after: $after
    sortBy: $sortBy
    sortRandomSeed: 0
  ) {
    pageInfo { hasNextPage endCursor }
    edges {
      node {
        id objectId objectType
        content(country: $country, language: $language) {
          title shortDescription originalReleaseYear
          genres { shortName }
          ageCertification
          scoring { imdbScore imdbVotes tmdbScore tomatoMeter }
        }
        offers(country: $country, platform: WEB) {
          monetizationType
          package { id packageId clearName technicalName }
        }
        streamingCharts(country: $country) {
          edges { streamingChartInfo { rank } }
        }
      }
    }
  }
}
"""

# ── User-agent rotation ───────────────────────────────────────────────────────

FALLBACK_UA = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/121.0.0.0 Safari/537.36",
]

try:
    _ua_lib = UserAgent(browsers=["chrome", "firefox", "safari"])

    def get_ua():
        try:
            return _ua_lib.random
        except Exception:
            return random.choice(FALLBACK_UA)
except Exception:

    def get_ua():
        return random.choice(FALLBACK_UA)

# ── Text helpers ──────────────────────────────────────────────────────────────


def clean(text: str) -> str:
    """Strip HTML tags and collapse whitespace."""
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", "", str(text))
    return re.sub(r"\s+", " ", text).strip()


def norm_rating(raw: str) -> str:
    """Normalise a raw age-certification string to a known rating label."""
    raw = raw.upper().strip()
    for k in [
        "TV-MA",
        "TV-14",
        "TV-PG",
        "TV-G",
        "TV-Y7",
        "TV-Y",
        "NC-17",
        "PG-13",
        "R",
        "PG",
        "G",
        "18+",
        "16+",
        "13+",
        "ALL",
    ]:
        if k in raw:
            return k
    return raw or "NR"


# ── Core fetch ────────────────────────────────────────────────────────────────


def fetch_page(
    session: requests.Session,
    country: str,
    language: str,
    package_ids: list[str],
    after: Optional[str] = None,
    page_size: int = 100,
    object_types: Optional[list[str]] = None,
    sort_by: str = "POPULAR",
) -> dict:
    """
    Send one GraphQL request to JustWatch and return the raw JSON dict.
    Raises requests.HTTPError on non-2xx responses.
    """
    hdrs = _base_headers(get_ua())
    payload = {
        "operationName": "GetProviderTitles",
        "query": GRAPHQL_QUERY,
        "variables": {
            "country": country,
            "language": language,
            "first": page_size,
            "after": after,
            "packageIds": package_ids,
            "objectTypes": object_types,
            "sortBy": sort_by,
        },
    }
    resp = session.post(GRAPHQL_URL, json=payload, headers=hdrs, timeout=15)
    resp.raise_for_status()
    return resp.json()


def parse_titles(
    raw_json: dict,
    platform: str,
    region: str,
    mode: str,
    seen: set,
) -> list[dict]:
    """
    Extract title dicts from a single page of JustWatch API response.

    Args:
        raw_json:  The parsed JSON from fetch_page().
        platform:  Platform name key (e.g. "netflix").
        region:    ISO country code (e.g. "US").
        mode:      "trending" or "catalog" — controls is_trending and ranking.
        seen:      Set of already-seen lowercase titles (mutated in place to
                   deduplicate within a scrape session).

    Returns:
        List of title dicts ready to insert into the DB.
    """
    keywords = PLATFORM_KEYWORDS[platform]
    edges = raw_json.get("data", {}).get("popularTitles", {}).get("edges", [])
    results = []

    for edge in edges:
        node = edge.get("node")
        if not node:
            continue
        try:
            content = node.get("content") or {}
            title = clean(content.get("title", ""))
            if not title or title.lower() in seen:
                continue

            # Belt-and-suspenders: confirm a FLATRATE offer exists on this platform
            offers = [
                o
                for o in (node.get("offers") or [])
                if any(
                    kw in str((o.get("package") or {}).get("technicalName", "")).lower()
                    for kw in keywords
                )
                and o.get("monetizationType") in ("FLATRATE", "FLATRATE_WITH_ADS")
            ]
            if not offers:
                continue

            scoring = content.get("scoring") or {}
            charts = node.get("streamingCharts", {}).get("edges", [])
            chart_rank = charts[0]["streamingChartInfo"]["rank"] if charts else 0
            is_trending = (
                chart_rank > 0
            )  # true whenever JustWatch has a chart rank for this title/region
            ranking = (
                chart_rank  # always store the real rank when JustWatch provides it
            )

            results.append(
                {
                    "scraped_at": __import__("datetime").datetime.now().isoformat(),
                    "platform": platform,
                    "region": region.upper(),
                    "title": title,
                    "content_type": "movie"
                    if node.get("objectType", "").upper() == "MOVIE"
                    else "tv",
                    "genre": ", ".join(
                        g.get("shortName", "")
                        for g in (content.get("genres") or [])
                        if g.get("shortName")
                    )
                    or "Unknown",
                    "release_year": str(content.get("originalReleaseYear", "") or ""),
                    "ranking_position": ranking,
                    "synopsis": clean(content.get("shortDescription", "") or ""),
                    "maturity_rating": norm_rating(
                        content.get("ageCertification", "") or ""
                    ),
                    "is_trending": is_trending,
                    "source_url": GRAPHQL_URL,
                    "imdb_score": float(scoring.get("imdbScore") or 0),
                    "imdb_votes": int(scoring.get("imdbVotes") or 0),
                    "tomatometer": int(scoring.get("tomatoMeter") or 0),
                    "tmdb_score": float(scoring.get("tmdbScore") or 0),
                }
            )
            seen.add(title.lower())

        except Exception as e:
            log.warning(f"Skipping node: {e}")

    return results


def get_page_info(raw_json: dict) -> dict:
    """Extract pageInfo from a raw JustWatch response."""
    return raw_json.get("data", {}).get("popularTitles", {}).get("pageInfo", {})
