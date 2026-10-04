"""사후 추가 실험(CEO-77) 채점용 블라인드. 본 실험 naive 답(answers.jsonl)과 사후 mix 답(answers_post_<tag>.jsonl)을
문항마다 A/B 로 섞어 grading/blind_post_<tag>.jsonl + grading/key_post_<tag>.json 을 만든다.
naive 답을 같이 넣는 이유: 채점자가 어느 쪽이 새 답인지 모르게 하고, naive 재채점이 본 채점과 얼마나 맞는지로 채점 일관성을 본다."""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

from blind import clean

HERE = Path(__file__).parent
G = HERE / "grading"


def main(tag: str) -> None:
    qs = {q["id"]: q for q in map(json.loads, (HERE / "questions.jsonl").read_text(encoding="utf-8").splitlines()) if q}
    naive = {r["id"]: r["answer"] for r in map(json.loads, (HERE / "answers.jsonl").read_text(encoding="utf-8").splitlines()) if r["mode"] == "naive"}
    post = {r["id"]: r for r in map(json.loads, (HERE / f"answers_post_{tag}.jsonl").read_text(encoding="utf-8").splitlines()) if r}
    rng = random.Random(20261004)
    key, rows = {}, []
    for qid in sorted(post):
        pair = [("naive", naive[qid]), (f"mix_post", post[qid]["answer"])]
        rng.shuffle(pair)
        key[qid] = {l: m for l, (m, _) in zip("AB", pair)}
        q = qs[qid]
        rows.append({"id": qid, "cat": q["cat"], "question": q["q"], "gold": q["gold"], "points": q.get("points"),
                     "evidence": q["evidence"], "answers": {l: clean(a) for l, (_, a) in zip("AB", pair)}})
    (G / f"blind_post_{tag}.jsonl").write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
    (G / f"key_post_{tag}.json").write_text(json.dumps(key, ensure_ascii=False, indent=1), encoding="utf-8")
    print(len(rows), "questions blinded ->", f"grading/blind_post_{tag}.jsonl")


if __name__ == "__main__":
    main(sys.argv[1])
