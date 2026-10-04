"""grading/grades.jsonl + grading/key.json -> results.md (모드별 정답률·범주별·문항별 승패)."""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).parent
G = HERE / "grading"
MODES = ["mix", "naive", "hybrid", "nocontext"]


def main() -> None:
    key = json.loads((G / "key.json").read_text(encoding="utf-8"))
    qs = {q["id"]: q for q in map(json.loads, (HERE / "questions.jsonl").read_text(encoding="utf-8").splitlines()) if q}
    s: dict[str, dict[str, float]] = defaultdict(dict)  # s[id][mode]
    for g in map(json.loads, (G / "grades.jsonl").read_text(encoding="utf-8").splitlines()):
        s[g["id"]][key[g["id"]][g["label"]]] = float(g["score"])
    missing = [(i, m) for i in qs for m in MODES if m not in s.get(i, {})]
    assert not missing, f"채점 누락: {missing[:5]}"
    n = len(qs)
    tot = {m: sum(s[i][m] for i in qs) for m in MODES}
    cats = sorted({q["cat"] for q in qs.values()}, key=["local", "multi", "global"].index)
    lines = ["# 결과 — LightRAG 1주차", "", "| 모드 | 점수 / %d | 정답률 |" % n, "|---|---:|---:|"]
    lines += [f"| {m} | {tot[m]:g} | {tot[m] / n:.1%} |" for m in MODES]
    diff = (tot["mix"] - tot["naive"]) / n
    lines += ["", f"**주 비교 mix − naive = {diff * 100:+.1f}%p** (통과 기준 +10%p = 3점)", ""]
    lines += ["| 범주 | n | " + " | ".join(MODES) + " |", "|---|---:|" + "---:|" * len(MODES)]
    for c in cats:
        ids = [i for i in qs if qs[i]["cat"] == c]
        lines.append(f"| {c} | {len(ids)} | " + " | ".join(f"{sum(s[i][m] for i in ids):g}" for m in MODES) + " |")
    w = sum(s[i]["mix"] > s[i]["naive"] for i in qs)
    l = sum(s[i]["mix"] < s[i]["naive"] for i in qs)
    lines += ["", f"문항별 mix 대 naive: 승 {w} · 패 {l} · 무 {n - w - l}", "",
              "| 문항 | 범주 | " + " | ".join(MODES) + " |", "|---|---|" + "---:|" * len(MODES)]
    lines += [f"| {i} | {qs[i]['cat']} | " + " | ".join(f"{s[i][m]:g}" for m in MODES) + " |" for i in qs]
    stats = HERE / "index_stats.md"  # 색인 통계·실행 조건 — 있으면 결과표 뒤에 붙인다
    if stats.exists():
        lines += ["", stats.read_text(encoding="utf-8").rstrip()]
    (HERE / "results.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[:10]))


if __name__ == "__main__":
    main()
