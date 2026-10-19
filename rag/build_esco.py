# Adapted from team V2: rag/build_esco.py (feature/agent-integration @ a5a03ff)
r"""ESCO ICT/data subset with graph links (T09).

Source: ESCO v1.1.1 (European Commission, CC BY 4.0) from the Tabiya CSV mirror (MIT repo; the data folder carries the
ESCO CC BY 4.0 licence), pinned commit + sha256 below, downloaded over HTTPS (no git). Same subset rule as V2:
skills linked to occupations of ISCO groups 25 / 35 / 212 / 1330, plus all transversal skills.

Writes:
  rag/data/esco/esco_ict_skills.jsonl   the V2 file, rebuilt (must be byte-identical to the copied one)
  rag/data/esco/esco_ict_graph.jsonl    per concept: uri, label, alt_labels, description, skill_type, reuse_level,
                                        broader (skills + skill groups), narrower (skills), related (skill-to-skill,
                                        both directions, essential/optional) as [{uri, label, in_subset}]
Usage: .venv\Scripts\python rag\build_esco.py
"""
import hashlib
import json
import urllib.request
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parent
SRC = ROOT / "data/raw/esco_tabiya"  # git-ignored download cache
OUT_V2 = HERE / "data/esco/esco_ict_skills.jsonl"
OUT = HERE / "data/esco/esco_ict_graph.jsonl"
BASE = ("https://raw.githubusercontent.com/tabiya-tech/taxonomy-model-application/"
        "eb3e5f445f6c0271641851dd2d27621d812c4662/data-sets/csv/esco-v1.1.2")
SHA256 = {
    "skills.csv": "9717a4521c94cc0eeefe519b2fccddac0a406a729d519bf3357e8ed60723fee2",
    "occupations.csv": "99ebee8b5d1ee376d00b0633b4e941167e37dcf0247ec7e8d4533a7a44dd7cfc",
    "occupation_to_skill_relations.csv": "28e4565583797edee7c3f20b743548cfefc9483683d549724ca69b2c9a9eb6d5",
    "skill_hierarchy.csv": "a6a39a2f3fe1198102ede4e2427fa995f9a242c52645a45c8bbd3a23c7c2cbf7",
    "skill_to_skill_relations.csv": "76d0f704eb64f7a35623e568d476604bd9601081d746b6e5bc914693bbee91f8",
    "skill_groups.csv": "e210d84d5e81d31a0b5fc7fad19141bba39c10f23706712d58ccf454f97be31a",
}
ISCO_PREFIX = r"^(25|35|212|1330)"  # V2: ICT professionals / technicians, mathematicians-statisticians, ICT managers


def fetch():
    SRC.mkdir(parents=True, exist_ok=True)
    for f, h in SHA256.items():
        p = SRC / f
        if not p.exists():
            urllib.request.urlretrieve(f"{BASE}/{f}", p)
        got = hashlib.sha256(p.read_bytes()).hexdigest()
        if got != h:
            raise SystemExit(f"hash mismatch for {f}: {got}")
    return {f: pd.read_csv(SRC / f, dtype=str, keep_default_na=False) for f in SHA256}


def subset(d):
    occ, rel, sk = d["occupations.csv"], d["occupation_to_skill_relations.csv"], d["skills.csv"]
    linked = set(rel[rel.OCCUPATIONID.isin(occ[occ.CODE.str.match(ISCO_PREFIX)].ID)].SKILLID)
    return sk[sk.ID.isin(linked) | (sk.REUSELEVEL == "transversal")].sort_values("ORIGINURI")


def alts(r):
    return [a for a in r.ALTLABELS.split("\n") if a and a != r.PREFERREDLABEL]


def build():
    d = fetch()
    keep = subset(d)
    # 1. the V2 file, rebuilt: proves the subset is the same as the one the Matcher used so far
    lines = []
    for r in keep.itertuples():
        a = alts(r)
        text = r.PREFERREDLABEL + (". Also known as: " + "; ".join(a) if a else "") + ". " + r.DESCRIPTION
        lines.append(json.dumps({"doc_id": r.ORIGINURI, "source_type": "esco", "title": r.PREFERREDLABEL,
                                 "skill_type": r.SKILLTYPE, "reuse_level": r.REUSELEVEL, "url": r.ORIGINURI,
                                 "text": text.strip()}, ensure_ascii=False))
    rebuilt = ("\n".join(lines) + "\n").encode("utf-8")
    same = rebuilt == OUT_V2.read_bytes()
    # 2. graph links
    sk, grp = d["skills.csv"], d["skill_groups.csv"]
    label = dict(zip(sk.ID, sk.PREFERREDLABEL)) | dict(zip(grp.ID, grp.PREFERREDLABEL))
    uri = dict(zip(sk.ID, sk.ORIGINURI)) | dict(zip(grp.ID, grp.ORIGINURI))
    ids = set(keep.ID)
    h, s2s = d["skill_hierarchy.csv"], d["skill_to_skill_relations.csv"]
    broader, narrower, related = {}, {}, {}
    skill_ids = set(sk.ID)
    for p, c, ct in zip(h.PARENTID, h.CHILDID, h.CHILDOBJECTTYPE):
        if ct == "skill":
            broader.setdefault(c, []).append(p)
            if p in skill_ids:
                narrower.setdefault(p, []).append(c)
    for a, t, b in zip(s2s.REQUIRINGID, s2s.RELATIONTYPE, s2s.REQUIREDID):
        related.setdefault(a, []).append((b, t))
        related.setdefault(b, []).append((a, t))

    def link(i, extra=None):
        return {"uri": uri[i], "label": label[i], "in_subset": i in ids} | (extra or {})

    with OUT.open("w", encoding="utf-8", newline="\n") as f:
        for r in keep.itertuples():
            f.write(json.dumps({
                "uri": r.ORIGINURI, "label": r.PREFERREDLABEL, "alt_labels": alts(r), "description": r.DESCRIPTION,
                "skill_type": r.SKILLTYPE, "reuse_level": r.REUSELEVEL,
                "broader": [link(i) for i in dict.fromkeys(broader.get(r.ID, [])) if i in uri],
                "narrower": [link(i) for i in dict.fromkeys(narrower.get(r.ID, [])) if i in uri],
                "related": [link(i, {"relation": t}) for i, t in dict.fromkeys(related.get(r.ID, [])) if i in uri],
            }, ensure_ascii=False) + "\n")
    stats = {"concepts": len(keep), "v2_file_rebuilt_identical": same,
             "with_broader": sum(bool(broader.get(i)) for i in keep.ID),
             "with_narrower": sum(bool(narrower.get(i)) for i in keep.ID),
             "with_related": sum(bool(related.get(i)) for i in keep.ID),
             "sha256": hashlib.sha256(OUT.read_bytes()).hexdigest()}
    print(json.dumps(stats))
    return stats


if __name__ == "__main__":
    build()
