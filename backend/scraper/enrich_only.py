"""
Standalone enrichment runner — called as a subprocess by /api/enrich.
Loads .env, runs enrich_from_db on the specified DB, streams log output.
"""

import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

_root = Path(__file__).parent.parent.parent
load_dotenv(_root / ".env")

from backend.scraper.enricher import enrich_from_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("Enricher")

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True)
    args = parser.parse_args()

    api_key = os.getenv("TMDB_API_KEY")
    if not api_key:
        print("ERROR: no TMDB_API_KEY available")
        sys.exit(1)

    log.info(f"Starting enrichment on {args.db}")
    enrich_from_db(Path(args.db), api_key=api_key)
    log.info("Enrichment complete.")
