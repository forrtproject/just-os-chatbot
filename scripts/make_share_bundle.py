"""Make the zip a teammate needs next to the Git repo to run JUST-OS (not in Git).

    python scripts/make_share_bundle.py            # .env + index + embedding-comparison vectors
    python scripts/make_share_bundle.py --minimal  # .env + index only (enough to run the bot)
    python scripts/make_share_bundle.py --no-env   # without your .env (teammates use their own keys)

Output: share/just-os-team-bundle.zip (share/ is git- and docker-ignored).
The teammate unzips it in the root of their clone; the files land in the right places.
Standard library only.
"""

import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "share" / "just-os-team-bundle.zip"

# (path, needed for) — the index is what the app loads (VECTOR_STORE)
RUN = [
    ("data/processed/vs_latest_bge-m3", "the bot: default index (bge-m3)"),
    ("data/raw/pub_years.csv", "the bot: publication years in the references (PUB_YEARS_FILE)"),
    ("data/raw/forrt_sheet1_261028.csv", "the bot: FORRT lookup mode (FORRT_SHEET_FILE)"),
]
COMPARE = [
    ("data/processed/vs_latest_bge-small-en-v1.5", "embedding comparison: E1 index + chunk texts"),
    ("data/processed/emb_cache", "embedding comparison: E2, E4, E5, E6 vectors"),
    ("data/raw/forrt_sheet2_261028.csv", "coverage audit and cluster PDF matching"),
    ("data/raw/forrt_db_250627.csv", "coverage audit: the sheet the index was built from"),
    ("data/interim/questions_and_text.csv", "eval/make_retrieval_set.py"),
    ("data/interim/cluster_pdf_metadata.csv", "cluster PDF matches so far (#17)"),
]

SETUP = """# JUST-OS team bundle

Contents (unzip in the root of your clone of forrtproject/just-os-chatbot, branch `main`):
{contents}

## Run the bot

1. Install Docker Desktop (Windows: with WSL2) and Git.
2. `git clone https://github.com/forrtproject/just-os-chatbot.git && cd just-os-chatbot`
3. Unzip this file in that folder (the paths inside the zip start at the repository root).
4. {env_step}
5. `docker compose up -d --build` (the first build takes 10-20 minutes).
6. One time, download the embedding and re-ranker models (about 3.5 GB, kept in a Docker volume):
   `docker compose exec web python -c "from sentence_transformers import SentenceTransformer, CrossEncoder; SentenceTransformer('BAAI/bge-m3'); CrossEncoder('BAAI/bge-reranker-base')"`
   then `docker compose restart web`.
7. Open http://localhost:8000 (chat) or http://localhost:8000/arena (model comparison).
8. Check: `docker compose exec web pytest test/ -q` (all tests pass).

More: README.md and docs/ in the repository. Do not commit anything from this bundle,
and do not share the keys in .env outside the team.
"""


def add_tree(archive, rel):
    path = ROOT / rel
    if not path.exists():
        sys.exit(f"Missing {rel}: build or download it first (see docs/data.md).")
    files = [p for p in sorted(path.rglob("*")) if p.is_file()] if path.is_dir() else [path]
    for file in files:
        archive.write(file, file.relative_to(ROOT).as_posix())
    return sum(f.stat().st_size for f in files)


if __name__ == "__main__":
    parts = list(RUN) if "--minimal" in sys.argv else RUN + COMPARE
    with_env = "--no-env" not in sys.argv and (ROOT / ".env").exists()
    OUT.parent.mkdir(exist_ok=True)

    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        lines = []
        if with_env:
            archive.write(ROOT / ".env", ".env")
            lines.append("- `.env`: settings and API keys (OpenRouter, OpenScholar) for the team")
        for rel, purpose in parts:
            size = add_tree(archive, rel)
            lines.append(f"- `{rel}{'/' if (ROOT / rel).is_dir() else ''}` ({size / 1e6:.0f} MB): {purpose}")
            print(f"added {rel} ({size / 1e6:.0f} MB)")
        env_step = (
            "`.env` is in the bundle. Change the keys to your own if the project lead asks you to."
            if with_env
            else "`cp .env.example .env` and add your own `OPENROUTER_API_KEY` (and `OPENSCHOLAR_API_KEY` if you have one)."
        )
        archive.writestr("TEAM_SETUP.md", SETUP.format(contents="\n".join(lines), env_step=env_step))

    print(f"{OUT.relative_to(ROOT)}: {OUT.stat().st_size / 1e6:.0f} MB" + (" (includes .env with keys)" if with_env else ""))
