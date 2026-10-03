"""채점용 블라인드 파일. answers.jsonl -> grading/blind.jsonl (모드 대신 무작위 라벨 A~D) + grading/key.json.
LightRAG 답변 끝의 참고문헌 목록(### References ...)은 모드를 드러내므로 지운다 — 무검색 답에는 그런 꼬리가 없다."""
from __future__ import annotations

import json
import random
import re
from pathlib import Path

HERE = Path(__file__).parent
G = HERE / "grading"
REF = re.compile(r"\n+#+\s*(References|참고\s*문헌|참고\s*자료|출처)\b.*\Z", re.S | re.I)
REF_ITEM = re.compile(r"\[(KG|DC)\]|\[\d+\]\s*[\w./-]+\.txt")


def clean(a: str) -> str:
    a = REF.sub("", a).strip()
    return REF_ITEM.sub("", a).strip()


def main() -> None:
    G.mkdir(exist_ok=True)
    qs = {q["id"]: q for q in map(json.loads, (HERE / "questions.jsonl").read_text(encoding="utf-8").splitlines()) if q}
    by_q: dict[str, dict[str, str]] = {}
    for r in map(json.loads, (HERE / "answers.jsonl").read_text(encoding="utf-8").splitlines()):
        by_q.setdefault(r["id"], {})[r["mode"]] = clean(r["answer"])
    rng = random.Random(20261003)
    key, rows = {}, []
    for qid, answers in sorted(by_q.items()):
        modes = sorted(answers)
        rng.shuffle(modes)
        labels = "ABCD"[: len(modes)]
        key[qid] = dict(zip(labels, modes))
        q = qs[qid]
        rows.append({"id": qid, "cat": q["cat"], "question": q["q"], "gold": q["gold"], "points": q.get("points"),
                     "evidence": q["evidence"], "answers": {l: answers[m] for l, m in zip(labels, modes)}})
    (G / "blind.jsonl").write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
    (G / "key.json").write_text(json.dumps(key, ensure_ascii=False, indent=1), encoding="utf-8")
    print(len(rows), "questions blinded")


if __name__ == "__main__":
    main()
