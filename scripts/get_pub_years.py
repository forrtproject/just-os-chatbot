"""Make the doi,year table for reference years (issue R1) from OpenAlex.

    python -m scripts.get_pub_years [index-dir] [output.csv]

Reads every DOI in the index docstore and asks OpenAlex (free, no key) for the
publication year, 50 DOIs per request. Standard library only.
Default: data/processed/vs_latest_bge-m3 → data/raw/pub_years.csv (tracked in Git).
"""

import csv
import json
import sys
import time
import urllib.parse
import urllib.request

from just_os.references import normalize_doi

OPENALEX = "https://api.openalex.org/works"
BATCH = 50


def index_dois(index_dir):
    nodes = json.load(open(f"{index_dir}/docstore.json", encoding="utf-8"))["docstore/data"]
    dois = set()
    for node in nodes.values():
        meta = node["__data__"]["metadata"]
        for key in ("doi", "link_to_resource"):
            value = meta.get(key)
            # a few documents store each value as a one-item dict (issue Q2)
            if isinstance(value, dict):
                value = next(iter(value.values()), None)
            if doi := normalize_doi(value):
                dois.add(doi)
                break
    return sorted(dois)


def fetch_years(dois):
    years = {}
    for start in range(0, len(dois), BATCH):
        batch = dois[start : start + BATCH]
        query = urllib.parse.urlencode(
            {"filter": "doi:" + "|".join(batch), "per-page": BATCH, "select": "doi,publication_year"}
        )
        with urllib.request.urlopen(f"{OPENALEX}?{query}", timeout=60) as response:
            for work in json.load(response)["results"]:
                doi = normalize_doi(work.get("doi"))
                if doi and work.get("publication_year"):
                    years[doi] = work["publication_year"]
        time.sleep(0.2)  # stay well under the OpenAlex rate limit
    return years


if __name__ == "__main__":
    index_dir = sys.argv[1] if len(sys.argv) > 1 else "data/processed/vs_latest_bge-m3"
    output = sys.argv[2] if len(sys.argv) > 2 else "data/raw/pub_years.csv"
    dois = index_dois(index_dir)
    years = fetch_years(dois)
    with open(output, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["doi", "year"])
        writer.writerows(sorted(years.items()))
    print(f"{len(years)} of {len(dois)} DOIs have a year → {output}")
