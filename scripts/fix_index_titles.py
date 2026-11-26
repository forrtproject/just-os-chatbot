"""Write the corrected titles of config/index_corrections.json into an index's metadata (no re-embedding).

    python -m scripts.fix_index_titles [INDEX_DIR ...]     # default: VECTOR_STORE

For every chunk whose title starts with a key of "titles", sets title, and doi / creators when given (link_to_resource
then becomes https://doi.org/<doi>). Keeps a copy of the docstore first (docstore.json.bak-<YYMMDD>, once a day).
Only metadata changes: the vectors were made from the chunk text, which is right. Run again after a rebuild.
"""

import json
import shutil
import sys
from datetime import date
from pathlib import Path

from config import settings


def fix(nodes: dict, titles: dict) -> int:
    """Fix the matching chunks in place; returns how many changed."""
    changed = 0
    for node in nodes.values():
        meta = node["__data__"]["metadata"]
        title = meta.get("title")
        title = next(iter(title.values()), "") if isinstance(title, dict) else str(title or "")
        right = next((v for k, v in titles.items() if title.startswith(k)), None)
        if right is None or title == right["title"]:
            continue
        meta["title"] = right["title"]
        if right.get("doi"):
            meta["doi"] = right["doi"]
            meta["link_to_resource"] = f"https://doi.org/{right['doi']}"
        if right.get("creators"):
            meta["creators"] = right["creators"]
        changed += 1
    return changed


def main(dirs):
    titles = json.loads(Path(settings.INDEX_CORRECTIONS_FILE).read_text(encoding="utf-8"))["titles"]
    for d in dirs:
        path = Path(d) / "docstore.json"
        backup = path.with_name(f"docstore.json.bak-{date.today():%y%m%d}")
        if not backup.exists():
            shutil.copyfile(path, backup)
        data = json.loads(path.read_text(encoding="utf-8"))
        changed = fix(data["docstore/data"], titles)
        path.write_text(json.dumps(data), encoding="utf-8")
        print(f"{d}: {changed} chunks retitled (backup {backup.name})")


if __name__ == "__main__":
    main(sys.argv[1:] or [settings.VECTOR_STORE])
