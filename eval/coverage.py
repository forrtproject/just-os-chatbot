"""Coverage audit (issue C1, #16): why is a FORRT resource not in the index?

    python eval/coverage.py [index-dir]

Reads the two FORRT sheets (data/raw/forrt_sheet{1,2}_*.csv, newest copy), the index
docstore, the June 2025 JUST-OS snapshot and its open-access list. Gives every unique
resource (by DOI, else title) one reason. Writes, with today's date:
  eval/results/coverage_<YYMMDD>.csv   one row per resource with its reason
  eval/results/coverage_<YYMMDD>.md    counts per reason (paste into a PR or the demo)
  eval/results/coverage_<YYMMDD>.svg   bar chart of the counts
"""

import json
import re
import sys
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from just_os.references import normalize_doi  # noqa: E402

RAW = Path("data/raw")
OA_LIST = Path("data/NWO JUST-OS/BOT/just-os_db_latest.csv")
RESULTS = Path("eval/results")

REASONS = {
    "indexed": "In the index",
    "excluded": "Excluded by curators",
    "doi_not_open_access": "DOI, checked: not open access (Unpaywall)",
    "doi_not_processed": "DOI, never processed (added after June 2025)",
    "video": "No DOI: video",
    "code_or_osf": "No DOI: OSF / GitHub page",
    "web_page": "No DOI: other web page",
    "no_link": "No DOI and no link",
}
VIDEO = ("youtube.com", "youtu.be", "vimeo.com")
CODE = ("osf.io", "github.com", "github.io", "gitlab.com")


def title_key(title) -> str:
    return re.sub(r"[^a-z0-9]", "", str(title or "").lower())


def newest(pattern):
    return sorted(RAW.glob(pattern))[-1]


def load_sheets() -> pd.DataFrame:
    s1 = pd.read_csv(newest("forrt_sheet1_*.csv"))
    url1 = next(c for c in s1.columns if c.startswith("URL/DOI"))
    s1 = pd.DataFrame(
        {
            "sheet": 1,
            "title": s1["Title"],
            "url": s1[url1],
            "doi": s1["DOI"].fillna(s1[url1]),
            "material_type": s1[next(c for c in s1.columns if c.startswith("Material Type"))],
            "excluded": s1["Exclude"].fillna(False).astype(bool),
        }
    )
    s2 = pd.read_csv(newest("forrt_sheet2_*.csv"))
    s2 = pd.DataFrame(
        {
            "sheet": 2,
            "title": s2["title"],
            "url": s2["url"],
            "doi": s2["DOI"].fillna(s2["url"]),
            "material_type": s2["material_type"],
            "excluded": False,
        }
    )
    rows = pd.concat([s1, s2], ignore_index=True)
    rows["doi"] = rows["doi"].map(normalize_doi)
    rows["key"] = rows["doi"].fillna(rows["title"].map(title_key))
    return rows[rows["key"] != ""].drop_duplicates("key")


def index_keys(index_dir) -> set:
    nodes = json.load(open(f"{index_dir}/docstore.json", encoding="utf-8"))["docstore/data"]
    keys = set()
    for node in nodes.values():
        meta = {
            k: next(iter(v.values()), None) if isinstance(v, dict) else v
            for k, v in node["__data__"]["metadata"].items()
        }
        keys.add(normalize_doi(meta.get("doi")) or normalize_doi(meta.get("link_to_resource")))
        keys.add(title_key(meta.get("title")))
    return keys - {None, ""}


def snapshot_dois():
    """DOIs the June 2025 pipeline saw, and those it found open access."""
    raw = pd.read_csv(RAW / "forrt_db_250627.csv")
    url = next(c for c in raw.columns if c.startswith("URL/DOI"))
    seen = {d for d in raw[url].map(normalize_doi) if isinstance(d, str)}
    oa = set()
    if OA_LIST.exists():
        oa = {d for d in pd.read_csv(OA_LIST)["doi"].map(normalize_doi) if isinstance(d, str)}
    return seen, oa


def reason(row, indexed, seen, oa) -> str:
    if row.key in indexed or title_key(row.title) in indexed:
        return "indexed"
    if row.excluded:
        return "excluded"
    if isinstance(row.doi, str):  # pandas gives NaN (truthy) for "no DOI"
        return "doi_not_open_access" if row.doi in seen and row.doi not in oa else "doi_not_processed"
    host = urlparse(str(row.url)).netloc.lower() if isinstance(row.url, str) else ""
    if not host:
        return "no_link"
    if host.endswith(VIDEO):
        return "video"
    if host.endswith(CODE):
        return "code_or_osf"
    return "web_page"


def svg_bars(counts: pd.Series) -> str:
    width, bar, gap, label_w = 760, 26, 8, 330
    top = int(counts.max())
    height = len(counts) * (bar + gap) + 20
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        'font-family="sans-serif" font-size="13">'
    ]
    for i, (key, n) in enumerate(counts.items()):
        y = 10 + i * (bar + gap)
        w = (width - label_w - 60) * n / top
        parts.append(f'<text x="{label_w - 8}" y="{y + 18}" text-anchor="end">{REASONS[key]}</text>')
        parts.append(f'<rect x="{label_w}" y="{y}" width="{w:.0f}" height="{bar}" fill="#2b6cb0"/>')
        parts.append(f'<text x="{label_w + w + 6:.0f}" y="{y + 18}">{n}</text>')
    parts.append("</svg>")
    return "\n".join(parts)


if __name__ == "__main__":
    index_dir = sys.argv[1] if len(sys.argv) > 1 else "data/processed/vs_latest_bge-m3"
    rows = load_sheets()
    indexed = index_keys(index_dir)
    seen, oa = snapshot_dois()
    rows["reason"] = [reason(r, indexed, seen, oa) for r in rows.itertuples()]

    counts = rows["reason"].value_counts().reindex(list(REASONS)).dropna().astype(int)
    stem = RESULTS / f"coverage_{date.today():%y%m%d}"
    rows[["sheet", "title", "doi", "url", "material_type", "reason"]].to_csv(f"{stem}.csv", index=False)
    lines = [
        f"Coverage of {len(rows)} unique FORRT resources (index: {index_dir})",
        "",
        "| Reason | Resources | Share |",
        "|---|---|---|",
    ]
    lines += [f"| {REASONS[k]} | {n} | {n / len(rows):.0%} |" for k, n in counts.items()]
    Path(f"{stem}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    Path(f"{stem}.svg").write_text(svg_bars(counts), encoding="utf-8")
    print("\n".join(lines))
