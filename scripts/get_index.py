"""Download the vector index and unpack it into data/processed/.

    python scripts/get_index.py <direct-download-URL-of-the-zip>
    INDEX_URL=<url> python scripts/get_index.py

The zip holds one folder, for example vs_latest_bge-m3/, with the files of a
llama-index FAISS index. Ask the project lead for the URL (it is not in Git).
Standard library only, so it runs before Docker is set up.
"""

import os
import shutil
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

TARGET = Path(__file__).resolve().parent.parent / "data" / "processed"
REQUIRED = {"default__vector_store.json", "docstore.json", "index_store.json"}

if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("INDEX_URL")
    if not url:
        sys.exit(__doc__)

    with tempfile.TemporaryDirectory() as tmp:
        archive = Path(tmp) / "index.zip"
        print(f"Downloading {url} ...")
        with urllib.request.urlopen(url) as response, open(archive, "wb") as f:
            shutil.copyfileobj(response, f)

        with zipfile.ZipFile(archive) as z:
            names = z.namelist()
            folders = {n.split("/")[0] for n in names if "/" in n}
            # Refuse paths that would leave the target folder
            if len(folders) != 1 or any(n.startswith("/") or ".." in n for n in names):
                sys.exit(f"Unexpected zip layout: {names[:5]}")
            folder = folders.pop()
            missing = REQUIRED - {Path(n).name for n in names}
            if missing:
                sys.exit(f"Not an index: {missing} missing in {folder}/")
            TARGET.mkdir(parents=True, exist_ok=True)
            z.extractall(TARGET)

    print(f"Index ready: {TARGET / folder}")
    print(f"It must match the settings: VECTOR_STORE=data/processed/{folder}")
