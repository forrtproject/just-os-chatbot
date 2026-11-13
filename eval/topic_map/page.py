"""Step 4: the corpus map page and a short summary, into eval/results/.

    python eval/topic_map/page.py [--work eval/.topic_map/latest] [--before eval/.topic_map/<older run>]

--before (the work folder of an earlier index) adds each sub-cluster's old score, so the page
shows which blind spots the new papers closed. Only the labelled eval questions are shown,
never chat questions. Writes:
  eval/results/topic_map_<YYMMDD>.html  the interactive page (works offline apart from fonts)
  eval/results/topic_map_<YYMMDD>.md    headline numbers, blind and thin sub-clusters, wrong files
  eval/results/topic_map_<YYMMDD>.csv   one row per FORRT sub-cluster
"""

import argparse
import json
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import WORK, embed, status  # noqa: E402

HERE = Path(__file__).resolve().parent


def page_data(work: Path, before: Path | None):
    c = pd.read_csv(work / "chunks.csv", low_memory=False)
    t = pd.read_csv(work / "topics.csv")
    s = pd.read_csv(work / "taxonomy_coverage.csv")
    q = pd.read_csv(work / "questions_scored.csv")
    src = (c.source == "cluster").to_numpy()

    pts = [[round(float(a), 2), round(float(b), 2), int(k), int(z)] for a, b, k, z in zip(c.x, c.y, c.topic, src)]
    cl_share = c.groupby("topic").source.apply(lambda x: float((x == "cluster").mean()))
    topics = [{"id": int(r.topic), "label": ", ".join(r.keywords.split(", ")[:3]), "kw": r.keywords,
               "chunks": int(r.chunks), "papers": int(r.papers), "p3": int(r.papers_3plus),
               "share": float(r.top_paper_share), "kind": r.kind, "fc": int(r.forrt_cluster_no),
               "fsub": r.forrt_sub_cluster, "top": r.top_papers[:300], "x": round(r.x, 2), "y": round(r.y, 2),
               "cl": round(cl_share.get(r.topic, 0.0), 2)} for r in t.itertuples()]

    # Sub-clusters: the 150 closest chunks (for the map highlight) and the share of cluster PDFs in the top 10
    X = np.load(work / "vectors.npy")
    real, doc = ~c.is_boilerplate.to_numpy(), c.doc_id.to_numpy()
    old = {}
    if before:
        b = pd.read_csv(before / "taxonomy_coverage.csv")
        old = {(int(x.cluster_no), x.sub_cluster): (x.paper10_sim, x.best_sim) for x in b.itertuples()}
    subs = []
    for x, n60, v in zip(s.itertuples(), s["papers_0.60"], embed(s.sub_cluster.tolist())):
        row = X @ v
        row[~real] = -1
        top = np.argsort(-row)[:3000]
        seen = {}
        for i in top:
            seen.setdefault(doc[i], src[i])
            if len(seen) == 10:
                break
        d = {"c": int(x.cluster_no), "name": x.sub_cluster, "pdfs": int(x.cluster_pdfs), "best": x.best_sim,
             "p10": x.paper10_sim, "n60": int(n60), "status": status(x.paper10_sim), "top": x.top_papers,
             "top10_cluster": int(sum(seen.values())),
             "pts": [[round(float(c.x[i]), 2), round(float(c.y[i]), 2), round(float(row[i]), 3)] for i in top[:150]]}
        if (d["c"], d["name"]) in old:
            d["p10_before"], d["best_before"] = old[(d["c"], d["name"])]
            d["status_before"] = status(d["p10_before"])
        subs.append(d)

    ev = q[q.expect.isin(["answer", "refuse"])]
    gate = [{"q": r.question, "e": r.expect, "route": r.route, "s": r.gate_score, "n": int(n)}
            for r, n in zip(ev.itertuples(), ev["papers_0.60"])]

    # Papers whose text is not what the title says (checked by hand from title_check.csv)
    wrong = json.load(open(HERE / "wrong_files.json", encoding="utf-8"))
    wrong_titles = json.load(open(HERE / "wrong_titles.json", encoding="utf-8"))
    tc = pd.read_csv(work / "title_check.csv")
    bad = [{"title": r.title, "doi": r.doi, "chunks": int(r.chunks), "sim": r.title_content_sim, "actual": wrong[r.doi]}
           for r in tc.itertuples() if r.doi in wrong]
    badtitles = []
    for r in tc.itertuples():
        key = next((k for k in wrong_titles if str(r.title).startswith(k[:40])), None)
        if key:
            badtitles.append({"title": r.title, "chunks": int(r.chunks), "sim": r.title_content_sim,
                              "actual": wrong_titles[key]})

    summary = {"papers": int(c.doc_id.nunique()), "chunks": len(c), "topics": len(t),
               "cluster_papers": int(c[src].doc_id.nunique()), "cluster_chunks": int(src.sum()),
               "boiler": round(float(c.is_boilerplate.mean()), 3), "boiler_n": int(c.is_boilerplate.sum()),
               "kinds": t.kind.value_counts().to_dict(), "blind": sum(x["status"] == "blind" for x in subs),
               "subs": len(subs), "questions": len(ev),
               "filename_titles": int(tc.title.fillna("").str.match(r"^C\d+ SC\d+").sum()),
               "extent": [float(c.x.min()), float(c.x.max()), float(c.y.min()), float(c.y.max())]}
    if old:
        summary["blind_before"] = sum(x.get("status_before") == "blind" for x in subs)
        summary["papers_before"] = int(pd.read_csv(before / "chunks.csv", usecols=["doc_id"]).doc_id.nunique())
    return {"summary": summary, "points": pts, "topics": topics, "subs": subs, "gate": gate,
            "bad": bad, "badtitles": badtitles}


def html(data: dict, index_name: str, day: str) -> str:
    S = data["summary"]
    fmt = "{:,}".format
    before = "papers_before" in S
    fill = {
        "__INDEX__": index_name, "__PAPERS__": fmt(S["papers"]), "__DATE__": day,
        "__CLUSTER_PAPERS__": fmt(S["cluster_papers"]), "__TOPICS__": fmt(S["topics"]),
        "__CHUNKS__": fmt(S["chunks"]), "__QUESTIONS__": fmt(S["questions"]),
        "__BEFORE_EYEBROW__": f" · compared with the {fmt(S['papers_before'])}-paper index before" if before else "",
        "__BLIND_HEADING__": (f"Blind spots went from {S['blind_before']} to {S['blind']}" if before
                              else f"{S['blind']} of {S['subs']} sub-clusters are blind"),
        "__BEFORE_RING__": (f"the hollow ring is where it was in the {fmt(S['papers_before'])}-paper index." if before
                            else ""),
        "__BEFORE_FOOTER__": f" Before: the {fmt(S['papers_before'])}-paper index." if before else "",
    }
    body = (HERE / "page_template.html").read_text(encoding="utf-8")
    for k, v in fill.items():
        body = body.replace(k, v)
    blob = json.dumps(data, separators=(",", ":")).replace("</", "<\\/")
    body = body.replace("__DATA__", blob)
    i = body.index("</style>") + len("</style>")
    head = ('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            '<style>:root{color-scheme:light}body{margin:0;font-size:14px}[hidden]{display:none!important}</style>\n')
    return head + body[:i] + "\n</head>\n<body>\n" + body[i:] + "\n</body>\n</html>\n"


def summary_md(data: dict, index_name: str, day: str) -> str:
    S, subs = data["summary"], data["subs"]
    was = lambda x: f" (was {x['p10_before']:.3f})" if "p10_before" in x else ""  # noqa: E731
    lines = [
        f"# Topic map of `{index_name}` ({day})", "",
        f"- {S['papers']:,} papers ({S['cluster_papers']} FORRT cluster PDFs), {S['chunks']:,} chunks, "
        f"{S['topics']} topics: {S['kinds'].get('topic', 0)} multi-paper, {S['kinds'].get('one paper', 0)} "
        f"from one paper, {S['kinds'].get('reference lists', 0)} reference lists",
        f"- Reference-list or near-empty chunks: {S['boiler']:.0%} ({S['boiler_n']:,})",
        f"- FORRT sub-clusters blind: {S['blind']} of {S['subs']}"
        + (f" (was {S['blind_before']} in the {S['papers_before']:,}-paper index)" if "blind_before" in S else ""),
        f"- Papers whose text is another work: {len(data['bad'])}; cluster papers with a wrong title: "
        f"{len(data['badtitles'])}; with the file name as title: {S['filename_titles']}", "",
        "Status = similarity of the sub-cluster name to its 10th-closest paper: blind < 0.56, thin < 0.59, "
        "covered < 0.63, strong >= 0.63. The name alone is the probe, so treat it as a guide to where to look.", "",
        "## Blind and thin sub-clusters", "",
        "| Cluster | Sub-cluster | Status | 10th paper | PDFs in folder |", "|---|---|---|---|---|",
    ]
    for x in sorted((x for x in subs if x["status"] in ("blind", "thin")), key=lambda x: x["p10"]):
        lines.append(f"| {x['c']} | {x['name']} | {x['status']} | {x['p10']:.3f}{was(x)} | {x['pdfs']} |")
    lines += ["", "## Papers whose text is another work", "", "| DOI | Title in the index | The text is | Chunks |",
              "|---|---|---|---|"]
    lines += [f"| {b['doi']} | {b['title']} | {b['actual']} | {b['chunks']} |" for b in data["bad"]]
    lines += ["", f"Interactive page: `topic_map_{day.replace('-', '')[2:]}.html`.", ""]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--work", type=Path, default=WORK / "latest")
    ap.add_argument("--before", type=Path)
    ap.add_argument("--index-name", default="vs_latest_bge-m3")
    ap.add_argument("--out", type=Path, default=Path("eval/results"))
    args = ap.parse_args()

    data = page_data(args.work, args.before)
    today = date.today()
    stem = args.out / f"topic_map_{today:%y%m%d}"
    day = f"{today.day} {today:%b %Y}"
    stem.with_suffix(".html").write_text(html(data, args.index_name, day), encoding="utf-8")
    stem.with_suffix(".md").write_text(summary_md(data, args.index_name, today.isoformat()), encoding="utf-8")
    cols = ["c", "name", "status", "p10", "p10_before", "best", "n60", "pdfs", "top10_cluster", "top"]
    pd.DataFrame(data["subs"]).reindex(columns=cols).rename(columns={
        "c": "cluster", "name": "sub_cluster", "p10": "paper10_sim", "p10_before": "paper10_sim_before",
        "best": "best_sim", "n60": "papers_0.60", "pdfs": "pdfs_in_folder", "top10_cluster": "cluster_pdfs_in_top10",
        "top": "top_papers"}).to_csv(stem.with_suffix(".csv"), index=False)
    print(json.dumps(data["summary"])[:400])
    print(f"wrote {stem}.html / .md / .csv")


if __name__ == "__main__":
    main()
