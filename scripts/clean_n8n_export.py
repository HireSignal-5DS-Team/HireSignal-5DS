r"""Remove instance-specific and personal fields from an `n8n export:workflow` file, in place.

n8n 2.43 exports `shared` (the owner's project, holding the owner's name and e-mail) and timestamps; they must not
go into the repo. Workflow ids, nodes, connections and settings (error workflow id) are kept, so the file re-imports.

Usage: .venv\Scripts\python scripts\clean_n8n_export.py n8n\hiresignal_v1.json n8n\hiresignal_errors.json
"""
import json
import re
import sys
from pathlib import Path

DROP = ("shared", "createdAt", "updatedAt", "versionMetadata", "activeVersionId", "versionCounter", "triggerCount")


def clean(path):
    p = Path(path)
    data = json.loads(p.read_text(encoding="utf-8"))
    wf = data[0] if isinstance(data, list) else data
    for k in DROP:
        wf.pop(k, None)
    wf["active"] = False  # activation is a local step (n8n/README.md)
    text = json.dumps(wf, indent=2, ensure_ascii=False) + "\n"
    assert not re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", text), f"{p}: an e-mail address is still inside"
    assert not any(n.get("credentials") for n in wf["nodes"]), f"{p}: credentials inside"
    p.write_text(text, encoding="utf-8", newline="\n")
    print(f"cleaned {p}: {len(wf['nodes'])} nodes")


if __name__ == "__main__":
    for f in sys.argv[1:]:
        clean(f)
