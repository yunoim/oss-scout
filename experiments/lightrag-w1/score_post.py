"""사후 추가 실험(CEO-77) 집계. grading/grades_post_<tag>.jsonl(메인 최종) + key_post_<tag>.json + answers_post_<tag>.jsonl
→ results.md 끝에 '## 사후 추가' 절을 붙인다(같은 tag 절이 있으면 바꾼다). 본 실험 표는 건드리지 않는다.
naive 점수는 본 실험 최종 채점(grading/grades.jsonl + key.json)을 그대로 쓴다 — 조건이 같아 답이 같다.
사용: python score_post.py <tag> "<조건 설명 한 줄>" """
from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).parent
G = HERE / "grading"


def main(tag: str, cond: str) -> None:
    qs = {q["id"]: q for q in map(json.loads, (HERE / "questions.jsonl").read_text(encoding="utf-8").splitlines()) if q}
    key_main = json.loads((G / "key.json").read_text(encoding="utf-8"))
    naive = {}
    for g in map(json.loads, (G / "grades.jsonl").read_text(encoding="utf-8").splitlines()):
        if key_main[g["id"]][g["label"]] == "naive":
            naive[g["id"]] = float(g["score"])
    key = json.loads((G / f"key_post_{tag}.json").read_text(encoding="utf-8"))
    mix, naive_re = {}, {}
    for g in map(json.loads, (G / f"grades_post_{tag}.jsonl").read_text(encoding="utf-8").splitlines()):
        m = key[g["id"]][g["label"]]
        (mix if m == "mix_post" else naive_re)[g["id"]] = float(g["score"])
    post = {r["id"]: r for r in map(json.loads, (HERE / f"answers_post_{tag}.jsonl").read_text(encoding="utf-8").splitlines()) if r}
    ids = [i for i in qs if i in post]
    n = len(ids)
    missing = [i for i in ids if i not in mix]
    assert not missing, f"채점 누락: {missing}"
    cfg = post[ids[0]]["config"]
    chunks = [post[i]["context"]["chunks"] if post[i].get("context") else None for i in ids]
    tm, tn = sum(mix[i] for i in ids), sum(naive[i] for i in ids)
    w = sum(mix[i] > naive[i] for i in ids)
    l = sum(mix[i] < naive[i] for i in ids)
    cats = sorted({qs[i]["cat"] for i in ids}, key=["local", "multi", "global"].index)
    lines = [f"## 사후 추가 — CEO-77 ({tag}, 2026-10-04) · 사전 등록 밖", "",
             f"조건: {cond}", "",
             f"설정: num_ctx {cfg['num_ctx']} · max_total_tokens {cfg['max_total_tokens']} · max_entity_tokens {cfg['max_entity_tokens']} · max_relation_tokens {cfg['max_relation_tokens']} (naive 는 본 실험 답·채점 재사용 — 조건 동일)", "",
             f"mix 최종 컨텍스트 청크 수: " + (f"최소 {min(c for c in chunks if c is not None)} · 최대 {max(c for c in chunks if c is not None)} · 0개인 문항 {sum(1 for c in chunks if c == 0)}" if any(c is not None for c in chunks) else "기록 없음"), "",
             f"| 모드 | 점수 / {n} | 정답률 |", "|---|---:|---:|",
             f"| mix(사후) | {tm:g} | {tm / n:.1%} |", f"| naive(본 실험) | {tn:g} | {tn / n:.1%} |", "",
             f"**mix(사후) − naive = {(tm - tn) / n * 100:+.1f}%p** (기준 +10%p = {n * 0.1:g}점) · 문항별 승 {w} · 패 {l} · 무 {n - w - l}", "",
             "| 범주 | n | mix(사후) | naive |", "|---|---:|---:|---:|"]
    for c in cats:
        cid = [i for i in ids if qs[i]["cat"] == c]
        lines.append(f"| {c} | {len(cid)} | {sum(mix[i] for i in cid):g} | {sum(naive[i] for i in cid):g} |")
    if naive_re:
        agree = sum(1 for i in ids if i in naive_re and abs(naive_re[i] - naive[i]) < 1e-9)
        lines += ["", f"채점 일관성: 블라인드에 섞은 naive 답을 다시 채점한 결과가 본 채점과 일치한 문항 {agree}/{len(naive_re)}"]
    lines += ["", "| 문항 | 범주 | mix(사후) | naive | mix 청크 |", "|---|---|---:|---:|---:|"]
    lines += [f"| {i} | {qs[i]['cat']} | {mix[i]:g} | {naive[i]:g} | {post[i]['context']['chunks'] if post[i].get('context') else '-'} |" for i in ids]
    section = "\n".join(lines) + "\n"
    rp = HERE / "results.md"
    txt = rp.read_text(encoding="utf-8")
    pat = re.compile(rf"\n## 사후 추가 — CEO-77 \({re.escape(tag)}.*?(?=\n## |\Z)", re.S)
    txt = pat.sub("", txt).rstrip() + "\n\n" + section
    rp.write_text(txt, encoding="utf-8")
    print(section)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
