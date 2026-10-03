"""law.go.kr 자치법규 XML(docs/raw_<ID>.xml) -> 본문 텍스트(docs/<ID>.txt).

원본은 2026-10-03 에 한 번만 받았다:
  https://www.law.go.kr/DRF/lawService.do?OC=<OC>&target=ordin&ID=<ID>&type=XML
조례·규칙은 저작권법 제7조(보호받지 못하는 저작물)에 해당한다. 다시 받으려면 본인 OC 를 발급받아 쓴다.
"""
from __future__ import annotations

import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

DOCS = Path(__file__).parent / "docs"
FETCHED = "2026-10-03"


def convert(raw: Path) -> Path:
    root = ET.parse(raw).getroot()
    info = root.find("자치법규기본정보")
    name = info.findtext("자치법규명").strip()
    lid = info.findtext("자치법규ID")
    lines = [
        f"# {name}",
        f"(출처: 국가법령정보센터 자치법규 ID {lid} · 시행일자 {info.findtext('시행일자')} · 수집 {FETCHED})",
        "",
    ]
    for jo in root.iter("조"):
        body = (jo.findtext("조내용") or "").strip()
        if body:
            lines.append(body)
            lines.append("")
    for tag in ("부칙내용", "별표내용"):
        for el in root.iter(tag):
            t = (el.text or "").strip()
            if t:
                lines.append(t)
                lines.append("")
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip() + "\n"
    out = DOCS / f"{lid}.txt"
    out.write_text(text, encoding="utf-8")
    return out


if __name__ == "__main__":
    for raw in sorted(DOCS.glob("raw_*.xml")):
        out = convert(raw)
        print(out.name, len(out.read_text(encoding="utf-8")), "chars", file=sys.stdout)
