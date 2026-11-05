"""Bounded, repeatable live-demo builder; always extracts the original PDF anew."""
from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import json
import math
import re
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode, urlsplit, unquote
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
PORTAL = "https://www.data.go.kr/data/15060880/fileData.do"
PRESS = "https://www.mpm.go.kr/mpm/comm/newsPress/newsPressRelease/?boardId=bbs_0000000000000029&cntId=4263&mode=view"
PAPER = "https://dcollection.korea.ac.kr/srch/srchDetail/000000068482"
DISPLAY_REFS = [
    ("APA 7판 7.5절 표·그림 본문 언급", "https://nool.ontariotechu.ca/writing/references-and-citations/american-psychological-association/apa-7th-edition-tables-and-figures.php"),
    ("Anscombe 1973, Graphs in Statistical Analysis", "https://doi.org/10.1080/00031305.1973.10478966"),
    ("Matejka, Fitzmaurice 2017, Same Stats, Different Graphs", "https://doi.org/10.1145/3025453.3025912"),
    ("Weissgerber 외 2015, Beyond Bar and Line Graphs", "https://doi.org/10.1371/journal.pbio.1002128"),
]
HEADERS = ["분야", "행 구분", "페이지", "선발예정인원", "응시대상인원", "응시인원", "단위", "선발 원문", "대상 원문", "응시 원문"]
ACCENT, MUTED, INK, PAPER_COLOR = "147D78", "B9C7C3", "183B3B", "F8F6F0"


def save(folder, name, content):
    (folder / name).write_text(content, encoding="utf-8")


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def get(url, **kwargs):
    import requests
    response = requests.get(url, timeout=(3, 7), headers={"User-Agent": "Mozilla/5.0"}, **kwargs)
    response.raise_for_status()
    return response


def source_pdf(folder):
    """At most three bounded requests; no repeated searches or retries."""
    try:
        response = get(PORTAL)
        html = response.text
        match = re.search(r"fn_fileDataDown\('15060880',\s*'(uddi:[^']+)'", html)
        require(match is not None, "PDF 다운로드 식별자를 찾지 못함")
        import requests
        result = requests.post("https://www.data.go.kr/tcs/dss/selectFileDataDownload.do", data={
            "publicDataDetailPk": match[1], "publicDataPk": "15060880", "atchFileId": "",
            "fileDetailSn": "1", "publicDataTyCode": "PR0051",
        }, headers={"Referer": PORTAL, "X-Requested-With": "XMLHttpRequest"}, timeout=(3, 7))
        result.raise_for_status()
        result = result.json()
        require(result.get("status") is True, "다운로드 응답 거절")
        url = "https://www.data.go.kr/cmm/cmm/fileDownload.do?" + urlencode({
            "atchFileId": result["atchFileId"], "fileDetailSn": result["fileDetailSn"],
        })
        raw = get(url).content
        require(raw.startswith(b"%PDF"), "응답이 PDF가 아님")
        (folder / "raw/raw.pdf").write_bytes(raw)
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        return {"archive": False, "download": url, "note": "공식 페이지에서 신규 확보", "page_verified": True,
                "page_title": soup.title.get_text(strip=True) if soup.title else "게시 제목 미확인"}
    except Exception as exc:
        archive = ROOT / "demo/cases/d-grade7"
        require((archive / "raw.pdf").exists() and (archive / "SOURCE.md").exists(), "공식 자료·보관본 모두 미확보; 수치 생성 중단")
        shutil.copy2(archive / "raw.pdf", folder / "raw/raw.pdf")
        shutil.copy2(archive / "SOURCE.md", folder / "raw/ARCHIVE_SOURCE.md")
        return {"archive": True, "download": None, "note": "공식 확보 실패: " + str(exc).splitlines()[0][:240], "page_verified": False}


def evidence_page(url, kind):
    from bs4 import BeautifulSoup
    try:
        soup = BeautifulSoup(get(url).text, "html.parser")
        text = soup.get_text(" ", strip=True)
        if kind == "press":
            match = re.search(r"선발\s*예정\s*인원\s*([\d,]+)명에\s*([\d,만\s]+)명이\s*지원해\s*평균\s*([\d.]+)대\s*1", text)
            require(match is not None, "경쟁률 본문 수치 확인 실패")
            summary = f"접수 기준 선발 예정 {match[1]}명, 지원 {match[2]}명, 경쟁률 {match[3]}대 1이에요. 실제 응시인원 기준과 구분해요."
            title, access = "국가공무원 7급 공채 경쟁률", "보도자료 본문"
        else:
            title = "지방공무원의 공직선택동기가 직무만족에 미치는 영향"
            require(title in text and "초록" in text and "설문" in text, "논문 초록 확인 실패")
            summary, access = "공직선택 이유를 설문으로 살펴본 연구예요. 이 시험 응시자에게 일반화할 수 없어요. 논문 본문은 읽지 않았어요.", "초록·목차; 논문 본문 미열람"
        return {"url": url, "kind": kind, "title": title, "summary": summary, "access": access, "verified": True, "via": "실행 중 HTTP 원문 열람"}
    except Exception as exc:
        return {"url": url, "kind": kind, "title": "경쟁률 보도자료" if kind == "press" else "지원 동기 연구", "verified": False, "access": "미확인", "summary": "원문을 확보하지 못했어요. 확인하지 못한 수치·연구 결과는 쓰지 않았어요.", "error": str(exc).splitlines()[0][:200]}


def extract(folder):
    import pdfplumber
    rows, independent = [], []
    with pdfplumber.open(folder / "raw/raw.pdf") as pdf:
        title = pdf.pages[0].extract_text().splitlines()[0]
        require("2026" in title and "7급" in title and "응시현황" in title, "원본 연도·제목 불일치; 다른 연도 대체 금지")
        for page_no, page in enumerate(pdf.pages, 1):
            text = page.extract_text()
            save(folder, f"raw/page-{page_no}.txt", text)
            for line in text.splitlines():
                match = re.match(r"^(.*?)\s+([\d,]+|-)\s+([\d,]+|-)\s+([\d,]+|-)$", line)
                if match:
                    independent.append(list(match.groups()))
            for table in page.extract_tables():
                for cells in table:
                    label = (cells[0] or "").replace("\n", " ").strip()
                    if not label or label == "모집단위":
                        continue
                    kind = "총계" if label == "총계" else "직군 계" if label.endswith(" 계") else "모집단위"
                    values = [None if not v or v == "-" else int(v.replace(",", "")) for v in cells[1:4]]
                    rows.append([label, kind, page_no, *values, "명", *cells[1:4]])
    require([[r[0], *r[7:10]] for r in rows] == independent, "표 추출/독립 텍스트 대조 실패")
    groups = sorted([r for r in rows if r[1] == "직군 계"], key=lambda r: r[5], reverse=True)
    total = next(r for r in rows if r[1] == "총계")
    require(len(groups) >= 2, "비교할 직군 부족")
    for col in (3, 4, 5):
        require(sum(r[col] for r in groups) == total[col], "직군 합계 불일치")
    for group in groups:
        start = rows.index(group) + 1
        end = next((i for i in range(start, len(rows)) if rows[i][1] != "모집단위"), len(rows))
        for col in (3, 4, 5):
            require(sum(r[col] for r in rows[start:end] if r[col] is not None) == group[col], "세부 합계 불일치")
    with (folder / "data.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(HEADERS)
        writer.writerows(rows)
    return rows, groups, total, title


def workbook(folder, rows, groups, sources):
    from openpyxl import Workbook
    from openpyxl.chart import BarChart, Reference
    from openpyxl.chart.series import DataPoint
    from openpyxl.styles import Font, PatternFill
    from openpyxl.chart.text import RichText
    from openpyxl.drawing.text import Paragraph, ParagraphProperties, CharacterProperties, Font as DFont
    book = Workbook()
    book.remove(book.active)
    tables = [("출처", [["찾은 주체", "자료", "주소", "조회일", "사용 여부"], *sources]),
              ("추출원문", [["페이지", "분야 원문", "선발 원문", "대상 원문", "응시 원문"], *[[r[2], r[0], *r[7:10]] for r in rows]]),
              ("정리데이터", [HEADERS, *rows]),
              ("비교표", [["분야", "실제 시험 본 사람 수 (명)"], *[[r[0].removesuffix(" 계"), r[5]] for r in groups]])]
    for name, data in tables:
        sheet = book.create_sheet(name)
        for row in data:
            sheet.append(row)
    ranks = {r[0]: i + 1 for i, r in enumerate(sorted(groups, key=lambda r: r[5] / r[3], reverse=True))}
    sheet = book.create_sheet("인기기준")
    sheet.append(["분야", "선발예정 (명)", "응시 (명)", "인원 순위", "선발 1명당 응시 (명)", "비율 순위"])
    for i, row in enumerate(groups, 2):
        sheet.append([row[0].removesuffix(" 계"), row[3], row[5], i - 1, f"=C{i}/B{i}", ranks[row[0]]])
        sheet.cell(i, 5).number_format = "0.00"
    axis_max = math.ceil(max(r[5] for r in groups) / 3000) * 3000
    for tag, highlight in [("A", 0), ("B", len(groups) - 1)]:
        chart = BarChart()
        chart.type = "bar"
        chart.title = f"{tag} · {groups[highlight][0].removesuffix(' 계')} 강조"
        chart.legend = None
        chart.add_data(Reference(book["비교표"], min_col=2, min_row=1, max_row=len(groups) + 1), titles_from_data=True)
        chart.set_categories(Reference(book["비교표"], min_col=1, min_row=2, max_row=len(groups) + 1))
        # openpyxl x_axis is the category axis even for horizontal bars.
        chart.x_axis.scaling.orientation = "maxMin"
        chart.y_axis.scaling.min, chart.y_axis.scaling.max, chart.y_axis.majorUnit = 0, axis_max, 3000
        chart.y_axis.title, chart.x_axis.title = "실제 시험 본 사람 수 (명)", "분야"
        for i in range(len(groups)):
            point = DataPoint(idx=i)
            point.graphicalProperties.solidFill = ACCENT if i == highlight else MUTED
            point.graphicalProperties.line.noFill = True
            chart.series[0].data_points.append(point)
        chart.txPr = RichText(p=[Paragraph(pPr=ParagraphProperties(defRPr=CharacterProperties(latin=DFont(typeface="Pretendard"), ea=DFont(typeface="Pretendard"))))])
        chart.width, chart.height = 23, 10
        book["비교표"].add_chart(chart, "D2" if tag == "A" else "D23")
    for sheet in book:
        sheet.freeze_panes, sheet.auto_filter.ref = "A2", sheet.dimensions
        for column in sheet.columns:
            sheet.column_dimensions[column[0].column_letter].width = 26
        for row in sheet:
            for cell in row:
                cell.font = Font(name="Pretendard", size=11)
        for cell in sheet[1]:
            cell.font = Font(name="Pretendard", bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor=ACCENT)
    book.save(folder / "report.xlsx")


def draw(folder):
    """Called by the Quarto cell; writes the exact same A/B figure as PNG."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.font_manager import FontProperties
    from matplotlib.ticker import StrMethodFormatter
    with (folder / "data.csv").open(encoding="utf-8-sig") as stream:
        groups = sorted([r for r in csv.DictReader(stream) if r["행 구분"] == "직군 계"], key=lambda r: int(r["응시인원"]), reverse=True)
    font = FontProperties(fname=str(folder / "figures/Pretendard.ttf"))
    from matplotlib.patches import FancyBboxPatch
    figure = plt.figure(figsize=(10, 8.4), layout="constrained", facecolor="#" + PAPER_COLOR)
    figure.get_layout_engine().set(h_pad=.25, w_pad=.25)
    panels = figure.subfigures(2, 1, hspace=.08)
    maximum = math.ceil(max(int(r["응시인원"]) for r in groups) / 3000) * 3000
    for panel, tag, highlight in zip(panels, ["A", "B"], [0, len(groups) - 1]):
        panel.set_facecolor("none")
        panel.patches.append(FancyBboxPatch((.01, .02), .98, .96, boxstyle="round,pad=0,rounding_size=.035", transform=panel.transSubfigure, facecolor="#FFFFFF", edgecolor="#" + MUTED, linewidth=1.2, zorder=-1))
        ax = panel.subplots()
        values = [int(r["응시인원"]) for r in groups]
        ax.set_facecolor("none")
        ax.barh(range(len(groups)), values, color=["#" + (ACCENT if i == highlight else MUTED) for i in range(len(groups))], height=.55)
        ax.set_yticks(range(len(groups)), [r["분야"].removesuffix(" 계") for r in groups], fontproperties=font)
        ax.invert_yaxis()
        ax.set_xlim(0, maximum)
        ax.set_xticks(range(0, maximum + 1, 3000))
        ax.xaxis.set_major_formatter(StrMethodFormatter("{x:,.0f}"))
        ax.set_xlabel("실제 시험 본 사람 수 (명)", fontproperties=font)
        ax.set_title(f"{tag} · {groups[highlight]['분야'].removesuffix(' 계')} 강조", fontproperties=font, fontsize=17, loc="left", color="#" + INK)
        for label in ax.get_xticklabels():
            label.set_fontproperties(font)
        for i, value in enumerate(values):
            ax.text(value + maximum * .012 if value < maximum * .85 else value - maximum * .012, i, f"{value:,}", ha="left" if value < maximum * .85 else "right", va="center", fontproperties=font)
        ax.spines[:].set_visible(False)
        ax.tick_params(length=0, colors="#" + INK, pad=6)
        ax.xaxis.label.set_color("#" + INK)
        ax.grid(axis="x", color="#" + MUTED, alpha=.45, linewidth=.8)
        ax.set_axisbelow(True)
    figure.savefig(folder / "figures/comparison.png", dpi=140)
    return figure


def documents(folder, args, rows, groups, total, title, acquisition, evidence):
    from fontTools.ttLib import TTFont
    font_path = ROOT / "slides/assets/fonts/PretendardVariable.woff2"
    # FreeType supports variable fonts; avoid expensive per-run font instancing.
    font = TTFont(font_path)
    font.flavor = None
    font.save(folder / "figures/Pretendard.ttf")
    generated_at = datetime.now(ZoneInfo("Asia/Seoul"))
    date = generated_at.date().isoformat()
    generated_label = generated_at.strftime("%Y-%m-%d %H:%M:%S KST (한국 시각)")
    generated_iso = generated_at.isoformat(timespec="seconds")
    save(folder, "generation.json", json.dumps({"generated_at": generated_iso, "timezone": "Asia/Seoul", "label": generated_label}, ensure_ascii=False, indent=2))
    sources = [["사람이 제공", "공식 게시 페이지", PORTAL, date, "접속 확인" if acquisition["page_verified"] else "신규 확보 실패; 게시정보·이용 조건 미확인"],
               ["사람이 제공" if acquisition["archive"] else "세롱이가 찾음", title, "raw/raw.pdf", date, "보관본 사용; 신규 다운로드 아님" if acquisition["archive"] else "신규 다운로드 사용"],
               ["세롱이가 찾음", "PDF 다운로드 주소", acquisition["download"] or "미확보", date, "사용" if acquisition["download"] else "사용 안 함"],
               ["사람이 제공", "보관본 출처 기록", "raw/ARCHIVE_SOURCE.md" if acquisition["archive"] else "../demo/cases/d-grade7/SOURCE.md", date, "사용" if acquisition["archive"] else "미사용"]]
    for name, url in DISPLAY_REFS:
        sources.append(["사람이 제공", name, url, date, "표현 근거로 사용; 세롱이 본문 미열람"])
    for record in evidence:
        sources.append(["세롱이가 찾음", record["title"], record["url"], record.get("checked_at", date), record["access"] + ("; 사용" if record["verified"] else "; 내용 미사용")])
    workbook(folder, rows, groups, sources)
    def md_table(headers, data):
        return "|" + "|".join(headers) + "|\n|" + "|".join("---" for _ in headers) + "|\n" + "\n".join("|" + "|".join(str(v) for v in r) + "|" for r in data)
    source_table = md_table(["찾은 주체", "자료", "주소", "조회일", "사용 여부"], [[who, name, f"[{name}]({url})" if url != "미확보" else url, day, use] for who, name, url, day, use in sources])
    save(folder, "SOURCE.md", "# 출처 기록\n\n" + source_table + "\n\n- 수집 기록 = " + acquisition["note"] + "\n- 기관 = 인사혁신처; 보관본 사용 시 제공 SOURCE.md 기준, 현재 게시정보 재검증 여부 별도\n- 이용 조건 = 사람 미확인\n- 원본 SHA256 = " + hashlib.sha256((folder / "raw/raw.pdf").read_bytes()).hexdigest() + "\n")
    encoded = base64.b64encode(font_path.read_bytes()).decode()
    save(folder, "report.scss", '''/*-- scss:defaults --*/
$body-bg: #f8f6f0;
$body-color: #183b3b;
$link-color: #147d78;
$font-family-sans-serif: "Pretendard";
/*-- scss:rules --*/
@font-face {font-family:Pretendard;src:url("data:font/woff2;base64,''' + encoded + '''") format("woff2");font-weight:100 900;}
:root {--paper:#f8f6f0;--ink:#183b3b;--accent:#147d78;}
body {font-family:Pretendard;background:var(--paper);color:var(--ink);line-height:1.8;word-break:keep-all;}
h1,h2 {color:var(--ink);letter-spacing:-.03em;} h2 {border-bottom:3px solid var(--accent);padding-bottom:.5rem;margin-top:2.5rem;}
a {color:var(--accent);} table {font-size:.9rem;width:100%;} .serongi {display:flex;align-items:center;gap:10px;margin:1rem 0;font-size:.85rem;}
.serongi img {width:40px;height:40px;} blockquote {border-left:4px solid var(--accent);padding:1rem;color:var(--ink);}
@media(prefers-color-scheme:dark) {:root {--paper:#132423;--ink:#e5eee8;--accent:#73d0c6;} figcaption {color:#a3d8d1!important;} }
''')
    next_steps = '''## 초안 다음, 우리가 할 일 {#next-steps}

- [ ] 확인해요 → [원본 PDF](raw/raw.pdf)·[정리 데이터](data.csv)의 숫자·빈칸을 대조하고 [엑셀](report.xlsx)의 차트 화면을 열어요. [출처 기록](SOURCE.md)·[공식 페이지](''' + PORTAL + ''')의 게시정보·이용 조건과 [논문](''' + PAPER + ''') 본문을 확인해요. [점검 기록](CHECK.md)의 미확인 항목을 갱신해요.
    - 나오는 것 = 아래 [우리 기록](#our-record)의 확인 칸에 확인한 것·남은 것
- [ ] 판단해요 → [인기 기준 절](report.html#popularity)과 [원고](report.qmd)를 보고 인기 사용 여부·기준·차트 A/B·미확인 처리 방침을 정해요.
    - 나오는 것 = [우리 기록](#our-record)의 결정 칸
- [ ] 우리 글로 수정해요 → [질문 절](report.html#question)·[원고](report.qmd)에 팀의 관심을 담은 첫 문장을 써요.
    - 나오는 것 = [우리 기록](#our-record)의 수정 칸, [재대조 결과](RECHECK.md)의 AI 초안 대비 바뀐 문장
- [ ] 다시 만들고 대조해요 → [실행 안내](README.md)대로 `python scripts/oneshot.py --recheck .`를 실행하거나 세롱이에게 요청해요. [생성 코드](scripts/oneshot.py)가 원본을 다시 추출해 [보고서](report.html#comparison)·[엑셀](report.xlsx)과 대조해요.
    - 나오는 것 = 새 [보고서](report.html)와 [재대조 결과](RECHECK.md): 숫자 대조·바뀐 문장·단계 체크·남은 미확인
- [ ] 공유해요 → [채팅 초안](team-chat.txt)을 고치고 [작성 과정](report.html#process)의 사람 확인자·날짜를 원고에서 갱신해요. 결과 폴더 구조를 유지하고 실제 공유 주소를 확인한 뒤 사람이 승인·직접 전송해요. HTML만 공유하면 별도 파일 링크는 열리지 않아요.
    - 나오는 것 = [우리 기록](#our-record)의 승인·공유 주소 칸, 확정한 [채팅 초안](team-chat.txt)

### 우리 기록 {#our-record}

- 확인: 사람 미확인
- 결정: 사람 미확인
- 수정 문장·이유: 사람 미확인
- 승인자·날짜: 사람 미확인
- 실제 공유 주소: 미확인(로컬 경로가 아니에요)
'''
    save(folder, "NEXT_STEPS.md", next_steps)
    (folder / "drafts").mkdir(exist_ok=True)
    save(folder, "RECHECK.md", "# 재대조 결과\n\n- 상태 = 아직 재대조 안 함\n- 실행 = `python scripts/oneshot.py --recheck .`\n- 나오는 것 = 숫자 재대조·AI 초안 대비 바뀐 문장·단계 체크 상태·남은 미확인\n")
    rank = {r[0]: i + 1 for i, r in enumerate(sorted(groups, key=lambda r: r[5] / r[3], reverse=True))}
    comparison = md_table(["분야", "실제 시험 본 사람 수 (명)"], [[r[0].removesuffix(" 계"), f"{r[5]:,}"] for r in groups])
    popularity = md_table(["분야", "응시인원 순위", "선발 (명)", "응시 (명)", "선발 1명당 응시 (명)", "비율 순위"], [[r[0].removesuffix(" 계"), i + 1, r[3], f"{r[5]:,}", f"{r[5]/r[3]:.2f}", rank[r[0]]] for i, r in enumerate(groups)])
    largest, ratio_top = groups[0], max(groups, key=lambda r: r[5] / r[3])
    conclusion = f"응시인원 기준으로는 {largest[0].removesuffix(' 계')} {largest[5]:,}명이 가장 많아요. 다만 선발 1명당 응시인원은 {ratio_top[0].removesuffix(' 계')} {ratio_top[5]/ratio_top[3]:.2f}명이 가장 높고, 지원 이유는 이 자료로 알 수 없어요."
    evidence_text = "\n\n".join(f"[{r['title']}]({r['url']}): {r['summary']} 열람 범위는 {r['access']}예요." for r in evidence)
    qmd = '''---
title: "어디에서 시험을 본 사람이 많았을까요?"
subtitle: "2026년 국가공무원 7급 공채 1차 · 팀 리포트 초안"
lang: ko
format:
  html:
    theme: [cosmo, report.scss]
    embed-resources: true
    toc: true
    toc-title: "목차"
    toc-expand: false
    include-after-body:
      text: |
        <style>#TOC .toc-fold{cursor:pointer;display:flex;align-items:center;gap:.4em;user-select:none}#TOC .toc-fold::after{content:"▾";transition:transform .2s}#TOC.toc-folded .toc-fold::after{transform:rotate(-90deg)}#TOC.toc-folded>ul{display:none}</style>
        <script>document.querySelectorAll("#TOC").forEach(function(n){var t=n.querySelector("h2");if(!t)return;t.classList.add("toc-fold");t.setAttribute("role","button");t.setAttribute("tabindex","0");t.setAttribute("aria-expanded","true");function f(){var c=n.classList.toggle("toc-folded");t.setAttribute("aria-expanded",String(!c));}t.addEventListener("click",f);t.addEventListener("keydown",function(e){if(e.key==="Enter"||e.key===" "){e.preventDefault();f();}});});</script>
jupyter: python3
execute:
  echo: false
  warning: false
---

<div class="serongi report-generated-at"><img src="../assets/serongi.svg" alt="" aria-hidden="true" width="40" height="40"><span>세롱이 (''' + args.agent + " / " + args.model + ''') - AI 글쓰기 도우미 by <time datetime="''' + generated_iso + '''">''' + generated_label + '''</time></span></div>

## 질문 {#question}

어느 분야에 실제 시험을 본 사람이 많았고, 이것을 인기라고 설명해도 될까요? 접수와 실제 응시를 구분해 살펴봐요.

''' + ("공식 자료 신규 확보에 실패해 제공된 2026년 보관본을 사용했어요." if acquisition["archive"] else "공식 페이지에서 원본 PDF를 새로 확보했어요.") + ''' 현재 게시정보·이용 조건의 확인 범위는 [출처 기록](SOURCE.md)에 남겼어요.

## 표와 두 표현 비교 {#comparison}

@tbl-comparison 은 분야별로 실제 시험을 본 사람 수예요.

''' + comparison + '''

: 분야별 실제 시험 본 사람 수 {#tbl-comparison}

```{python}
#| label: fig-comparison
#| fig-cap: "같은 숫자·축·정렬·단위로 강조만 바꿨어요."
from pathlib import Path
import sys
sys.path.insert(0, 'scripts')
from oneshot import draw
from IPython.display import display, Image
draw(Path.cwd())
display(Image(filename='figures/comparison.png'))
```

@fig-comparison 에서 A는 가장 큰 인원 규모, B는 상대적으로 작은 분야에 시선이 가도록 강조했어요. [엑셀](report.xlsx)에도 같은 비교표를 참조하는 편집 가능한 두 차트가 있어요.

같은 숫자라도 무엇을 강조하느냐에 따라 먼저 읽히는 내용이 달라져요. 요약값이 같아도 분포는 전혀 다를 수 있고([Anscombe 1973](''' + DISPLAY_REFS[1][1] + '''), [Matejka, Fitzmaurice 2017](''' + DISPLAY_REFS[2][1] + ''')), 연구 논문에서도 분포를 가리는 막대그래프가 흔히 쓰여요([Weissgerber 외 2015](''' + DISPLAY_REFS[3][1] + ''')). 그래서 두 표현을 함께 보여 주고, 그림을 번호로 부르며 무엇을 볼지 밝혔어요([APA 7판 7.5절](''' + DISPLAY_REFS[0][1] + ''')).

## 자료로 알 수 있는 사실 {#facts}

''' + f"직군 계 {len(groups)}개의 응시인원을 더하면 {total[5]:,}명이에요. 총계와 세부 모집단위는 중복 합산하지 않았어요. 원문의 '-'는 0으로 확정하지 않고 빈칸으로 보존했어요." + '''

## 인기라고 말할 수 있을까요 {#popularity}

‘인기’는 기준을 먼저 정해야 해요. 응시인원은 규모, 선발 1명당 응시인원·접수 경쟁률은 상대 수요, 여러 해 추이는 변화, 지원 동기 조사는 선호 이유를 살피는 기준 후보예요.

''' + popularity + '''

선발 1명당 응시인원은 실제 응시인원 ÷ 선발예정인원으로 계산했어요. ''' + f"전체는 {total[5]:,} ÷ {total[3]:,} = {total[5]/total[3]:.2f}명이에요. 원본 응시대상 {total[4]:,}명과 보도자료의 접수인원은 정의·시점이 다를 수 있어 같은 모집단으로 가정하지 않았어요. 차이 원인은 미확인이에요." + '''

''' + evidence_text + '''

> ''' + conclusion + '''

## 아직 알 수 없는 이유 {#limits}

이 자료는 ‘어디서 시험을 본 사람이 많았나’까지 답해요. 왜 골랐나·선호하나는 알 수 없어요. 동기 설문과 여러 해의 같은 정의 자료, 응시 자격·선발 규모를 더 확인해야 해요.

## 작성 과정 기록 {#process}

|단계|<img src="../assets/serongi.svg" alt="" aria-hidden="true" width="40" height="40" style="vertical-align:middle"> 세롱이|사람|
|---|---|---|
|함께 쓴 도우미|[표·차트 위 제작 표기](#comparison)를 참고해요|확인자·날짜 미확인이에요|
|수집|원본 연도·제목과 사용 경로를 기록했어요|게시정보·이용 조건 미확인이에요|
|정리|원본을 새로 추출하고 표·독립 텍스트·합계를 대조했어요|숫자 직접 대조 미확인이에요|
|제작·검증|엑셀 정의·HTML·내장 자산·링크를 점검해요. 결과는 CHECK.md에 남겨요|엑셀 화면 미확인이에요|
|판단·공유|기준과 한계를 밝히고 채팅 초안만 만들었어요|표현 선택·수정·승인·전송은 사람이 할 일이에요|

{{< include NEXT_STEPS.md >}}

## 출처 {#sources}

''' + source_table + '''

## 윤리적 사용 가이드 {#ethics}

세롱이는 출처 추적·원문 보존·추출과 집계 점검·오류 수정·AI 작업 공개를 맡아요. 수치·인용·출처를 조작하지 않고, 과장 해석을 피하며 한계를 밝혀요.

사람은 공유 전 원본·해석·이용 조건을 확인하고 승인해요. 세롱이는 사람 검토·승인을 대신하지 않아요. 개인정보·비공개 자료를 무단 수집하거나 외부로 전송하지 않아요.
'''
    save(folder, "report.qmd", qmd)
    save(folder, "team-chat.txt", conclusion + "\n원본·엑셀 화면·이용 조건과 미확인 항목을 함께 확인해요.\n표현을 고친 뒤 사람이 승인·직접 공유해요.\n사람이 확인한 실제 공유 주소: [미확인]\n")
    for name in ["report.qmd", "team-chat.txt"]:
        shutil.copy2(folder / name, folder / "drafts" / name)
    save(folder, "README.md", "# 재실행\n\n- 환경 = Python·pdfplumber·openpyxl·matplotlib·fonttools·brotli·requests·beautifulsoup4·jupyter·Quarto 사전 준비\n- 원본 추출·엑셀·AI 초안 재생성 = `python scripts/oneshot.py --rebuild .`; 사람 수정본 별도 보존 필요\n- 사람 수정 후 재렌더·재대조 = `python scripts/oneshot.py --recheck .` → [RECHECK.md](RECHECK.md)\n- AI 초안 보관 = [drafts/](drafts/); 재대조의 바뀐 문장 비교 기준\n- 사람 수정 원고만 렌더 = `quarto render report.qmd`\n- 생성 코드는 원래 프로젝트 assets·slides 경로 필요; HTML은 폰트·로고·PNG 내장\n- 별도 파일 링크 = 결과 폴더 구조 유지; 실제 공유 주소는 사람이 확인\n- 다음 행동 = [NEXT_STEPS.md](NEXT_STEPS.md); 검증 = [CHECK.md](CHECK.md)\n")


def verify(folder, rows, groups):
    from bs4 import BeautifulSoup
    from openpyxl import load_workbook
    book = load_workbook(folder / "report.xlsx")
    require(book.sheetnames == ["출처", "추출원문", "정리데이터", "비교표", "인기기준"], "시트 누락")
    charts = book["비교표"]._charts
    require(len(charts) == 2, "편집 가능한 차트 개수 불일치")
    maximum = math.ceil(max(r[5] for r in groups) / 3000) * 3000
    for i, chart in enumerate(charts):
        series = chart.series[0]
        require(series.val.numRef.f == f"'비교표'!$B$2:$B${len(groups)+1}", "차트 수치 참조 오류")
        require(series.cat.numRef.f == f"'비교표'!$A$2:$A${len(groups)+1}", "차트 분류 참조 오류")
        require((chart.y_axis.scaling.min, chart.y_axis.scaling.max, chart.y_axis.majorUnit, chart.x_axis.scaling.orientation) == (0, maximum, 3000, "maxMin"), "차트 축·정렬 오류")
        expected = [ACCENT if j == (0 if i == 0 else len(groups)-1) else MUTED for j in range(len(groups))]
        require([p.graphicalProperties.solidFill.srgbClr for p in series.data_points] == expected, "차트 강조색 오류")
    require([book["비교표"].cell(i+2, 2).value for i in range(len(groups))] == [r[5] for r in groups], "비교표 수치 오류")
    for i, row in enumerate(rows, 2):
        require([book["정리데이터"].cell(i, j).value for j in range(1, 11)] == row, "엑셀 원본 추출값 불일치")
    html = (folder / "report.html").read_text(encoding="utf-8")
    soup = BeautifulSoup(html, "html.parser")
    generation = json.loads((folder / "generation.json").read_text(encoding="utf-8"))
    timestamp = soup.select_one(".report-generated-at time")
    require(timestamp is not None and timestamp.get("datetime") == generation["generated_at"] and timestamp.get_text(strip=True) == generation["label"], "보고서 생성 날짜시간 표시 불일치")
    require(datetime.fromisoformat(generation["generated_at"]).utcoffset().total_seconds() == 9 * 3600, "생성 시각 한국 시간대 오류")
    require("data:font/woff2;base64," in unquote(html), "폰트 내장 누락")
    require(len(soup.select(".serongi")) == 1, "도우미 제작 표기는 한 곳만 허용")
    require(len(soup.select(".serongi img[alt=\"\"][aria-hidden=\"true\"]")) == 1, "도우미 얼굴 대체 텍스트 중복")
    require(soup.get_text().count("AI 글쓰기 도우미 by") == 1, "도우미 제작 문구 중복")
    require(any(i.get("src", "").startswith("data:image/svg+xml") for i in soup.select(".serongi img")), "로고 내장 누락")
    require(any(i.get("src", "").startswith("data:image/png") for i in soup.select("img")), "PNG 내장 누락")
    for link in soup.select("a[href]"):
        url = urlsplit(link["href"])
        if url.scheme or not url.path:
            if not url.scheme and url.fragment:
                require(soup.find(id=unquote(url.fragment)) is not None, "HTML 앵커 누락: " + url.fragment)
            continue
        target = folder / unquote(url.path)
        require(target.exists(), "로컬 링크 누락: " + str(target))
        if url.fragment:
            require(BeautifulSoup(target.read_text(encoding="utf-8"), "html.parser").find(id=url.fragment) is not None, "링크 절 누락")
    return [f"원본 {len(rows)}행·{len(rows)*3}개 수치/결측을 표 추출/독립 텍스트로 대조", "직군 계·모집단위·총계 합계 확인; 결측 유지", "엑셀 5시트·편집 가능 차트 2개 재열기; 참조·수치·축·정렬·강조색 확인", "Quarto 실제 렌더·폰트/로고/PNG 내장·HTML 전체 로컬 링크/앵커 확인", "생성 날짜시간·한국 시각(UTC+09:00)·generation.json/HTML 일치 확인"]


def worker(args, folder):
    started = time.perf_counter()
    stages = []
    def stage(name):
        stages.append({"stage": name, "elapsed_seconds": round(time.perf_counter() - started, 3)})
        print(f"[{stages[-1]['elapsed_seconds']:.1f}초] {name}", flush=True)
    for name in ["raw", "figures", "scripts"]:
        (folder / name).mkdir(exist_ok=True)
    shutil.copy2(__file__, folder / "scripts/oneshot.py") if Path(__file__).resolve() != (folder / "scripts/oneshot.py").resolve() else None
    if args.rebuild:
        acquisition = json.loads((folder / "run-input.json").read_text(encoding="utf-8"))["acquisition"]
        evidence = json.loads((folder / "evidence.json").read_text(encoding="utf-8"))
    else:
        # HTTP fetches overlap; no sub-agents or long sequential network waits.
        with ThreadPoolExecutor(max_workers=3) as pool:
            pdf_task = pool.submit(source_pdf, folder)
            if args.evidence:
                evidence = json.loads(Path(args.evidence).read_text(encoding="utf-8-sig"))
                require({r["kind"] for r in evidence} == {"press", "paper"}, "보도자료·논문 근거 두 종류 필요")
                for record in evidence:
                    require(record.get("checked_at") and record.get("via"), "외부 근거 열람일·방법 필요")
            else:
                tasks = [pool.submit(evidence_page, PRESS, "press"), pool.submit(evidence_page, PAPER, "paper")]
                evidence = [task.result() for task in tasks]
            acquisition = pdf_task.result()
    save(folder, "evidence.json", json.dumps(evidence, ensure_ascii=False, indent=2))
    save(folder, "run-input.json", json.dumps({"acquisition": acquisition, "agent": args.agent, "model": args.model, "root": str(ROOT)}, ensure_ascii=False, indent=2))
    stage("자료 확보·출처 기록")
    rows, groups, total, title = extract(folder)
    stage("원본 새 추출·표/텍스트·합계 대조")
    documents(folder, args, rows, groups, total, title, acquisition, evidence)
    stage("엑셀·원고·테마·후속 체크리스트 생성")
    save(folder, "CHECK.md", "# 점검 중\n\n- 사람 확인 = 미확인\n")
    quarto = shutil.which("quarto") or "C:/Program Files/Quarto/bin/quarto.exe"
    remaining = max(1, min(100, args.worker_budget - (time.perf_counter() - started) - 25))
    with (folder / "render.log").open("w", encoding="utf-8") as log:
        result = subprocess.run([quarto, "render", "report.qmd"], cwd=folder, stdout=log, stderr=subprocess.STDOUT, timeout=remaining)
    require(result.returncode == 0 and (folder / "report.html").exists(), "Quarto 실패; render.log 확인")
    stage("Quarto 렌더·차트 PNG 생성")
    checks = verify(folder, rows, groups)
    # Browser inspection is bounded and never triggers an install.
    browser_note = "브라우저 미검증"
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True, timeout=5000)
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.set_default_timeout(5000)
            page.goto((folder / "report.html").as_uri(), timeout=5000)
            page.evaluate("document.fonts.ready")
            require(page.evaluate("document.fonts.check('16px Pretendard')"), "폰트 로딩 실패")
            page.screenshot(path=str(folder / "figures/screen-light.png"))
            light = page.evaluate("getComputedStyle(document.body).backgroundColor")
            page.emulate_media(color_scheme="dark")
            page.screenshot(path=str(folder / "figures/screen-dark.png"))
            require(light != page.evaluate("getComputedStyle(document.body).backgroundColor"), "다크 모드 전환 실패")
            browser.close()
            browser_note = "Chromium 폰트 로딩·라이트/다크 배경 전환·화면 캡처 확인"
    except (ImportError, RuntimeError) as exc:
        browser_note += ": " + str(exc).splitlines()[0]
    except Exception as exc:
        # Browser unavailability is explicitly a remaining check, never a pass.
        browser_note += ": " + str(exc).splitlines()[0]
    stage("엑셀 재열기·HTML·링크·가용 브라우저 점검")
    save(folder, "CHECK.md", "# 점검 기록\n\n## 세롱이 확인\n\n" + "\n".join("- " + c for c in checks) + "\n- " + browser_note + "\n- 자료 접근·사용 여부 = [SOURCE.md](SOURCE.md) 및 [evidence.json](evidence.json)\n\n## 사람 미확인\n\n- 원본 직접 대조·엑셀 차트 화면·이용 조건·논문 본문\n- 인기 기준·표현 선택·문장 수정·승인·실제 공유 주소\n- 실제 전송 없음\n")
    save(folder, "timing.json", json.dumps({"worker_seconds": round(time.perf_counter() - started, 3), "stages": stages, "status": "complete"}, ensure_ascii=False, indent=2))


def changed_lines(before_path, after_path):
    import difflib
    if not before_path.exists():
        return ["AI 초안 보관본 없음 → 비교 불가"]
    before = before_path.read_text(encoding="utf-8").splitlines()
    after = after_path.read_text(encoding="utf-8").splitlines()
    lines = [line for line in difflib.unified_diff(before, after, lineterm="", n=0) if line[:1] in "+-" and line[:3] not in ("+++", "---")]
    return [("AI 초안: " if line[0] == "-" else "우리 글: ") + line[1:].strip() for line in lines if line[1:].strip()][:40] or ["바뀐 문장 없음"]


def step_state(folder):
    text = (folder / "NEXT_STEPS.md").read_text(encoding="utf-8")
    steps = [(mark.lower() == "x", name) for mark, name in re.findall(r"^- \[( |x|X)\] (\S+)", text, re.M)]
    records = re.findall(r"^- (확인|결정|수정 문장·이유|승인자·날짜|실제 공유 주소): (.*)$", text, re.M)
    return steps, records


def recheck(folder):
    before_csv = (folder / "data.csv").read_bytes()
    results = []
    try:
        rows, groups, total, title = extract(folder)
        same_csv = (folder / "data.csv").read_bytes() == before_csv
        if not same_csv:
            (folder / "data.csv").write_bytes(before_csv)
        results.append(("원본 재추출·합계", "통과", f"{len(rows)}행·직군 {len(groups)}개·총계 응시 {total[5]:,}명"))
        results.append(("data.csv ↔ 원본", "통과" if same_csv else "불일치", "재추출값과 같음" if same_csv else "사람 수정 또는 손상; 원래 파일 유지"))
    except Exception as exc:
        rows = groups = None
        results.append(("원본 재추출·합계", "실패", str(exc)))
    quarto = shutil.which("quarto") or "C:/Program Files/Quarto/bin/quarto.exe"
    rendered = subprocess.run([quarto, "render", "report.qmd"], cwd=folder, capture_output=True, text=True, encoding="utf-8", errors="replace")
    results.append(("Quarto 재렌더", "통과" if rendered.returncode == 0 else "실패", "report.html 새로 생성" if rendered.returncode == 0 else rendered.stderr.strip().splitlines()[-1:]))
    if rows and rendered.returncode == 0:
        try:
            verify(folder, rows, groups)
            results.append(("엑셀·HTML·링크", "통과", "차트 정의·내장 자산·로컬 링크·앵커 확인"))
        except Exception as exc:
            results.append(("엑셀·HTML·링크", "실패", str(exc)))
        html_text = (folder / "report.html").read_text(encoding="utf-8")
        missing = [r[0].removesuffix(" 계") for r in groups if f"{r[5]:,}" not in html_text]
        results.append(("보고서 숫자 ↔ 원본", "통과" if not missing else "불일치", "직군별 응시인원 모두 표기" if not missing else "누락: " + ", ".join(missing)))
        results.append(("우리 글 절 포함", "통과" if 'id="next-steps"' in html_text else "실패", "초안 다음, 우리가 할 일 절 존재 확인"))
    steps, records = step_state(folder)
    pending = [name for done, name in steps if not done] + [key for key, value in records if "미확인" in value]
    lines = ["# 재대조 결과", "", "- 실행 = " + datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d %H:%M:%S KST"), "- 대상 = [보고서](report.html)·[엑셀](report.xlsx)·[정리 데이터](data.csv)·[원본 PDF](raw/raw.pdf)", "", "## 숫자·렌더 재대조", "", "|점검|결과|내용|", "|---|---|---|"]
    lines += [f"|{name}|{status}|{detail if isinstance(detail, str) else ' '.join(detail)}|" for name, status, detail in results]
    lines += ["", "## 단계 체크", "", "|단계|상태|", "|---|---|"] + [f"|{name}|{'완료 표시' if done else '미완료'}|" for done, name in steps]
    lines += ["", "## 우리 기록", ""] + [f"- {key}: {value}" for key, value in records]
    lines += ["", "## 바뀐 문장 — 원고", ""] + ["- " + line for line in changed_lines(folder / "drafts/report.qmd", folder / "report.qmd")]
    lines += ["", "## 바뀐 문장 — 채팅 초안", ""] + ["- " + line for line in changed_lines(folder / "drafts/team-chat.txt", folder / "team-chat.txt")]
    lines += ["", "## 남은 미확인", ""] + (["- " + p for p in pending] or ["- 없음 → 사람 승인 후 직접 공유"])
    lines += ["", "- 세롱이 점검만 기록함; 사람 확인·승인 대행 안 함", ""]
    save(folder, "RECHECK.md", "\n".join(lines))
    for name, status, _ in results:
        print(f"{status}: {name}")
    print(f"단계 {sum(d for d, _ in steps)}/{len(steps)} 완료 표시 · 남은 미확인 {len(pending)}개\n결과: {folder / 'RECHECK.md'}")
    require(all(status == "통과" for _, status, _ in results), "재대조 불일치 있음; RECHECK.md 확인")


def main():
    global ROOT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Check the prepared environment without generating files")
    parser.add_argument("--agent", default="codex")
    parser.add_argument("--model", default="모델명 미확인")
    parser.add_argument("--evidence", help="Live browser-tool evidence JSON; never a processed data table")
    parser.add_argument("--started-at", help="UTC ISO time at receipt of the user's request; includes agent preparation")
    parser.add_argument("--rebuild", help="Re-extract preserved original; regenerates the AI draft")
    parser.add_argument("--recheck", help="Re-render the human-edited report and write RECHECK.md")
    parser.add_argument("--worker", help=argparse.SUPPRESS)
    parser.add_argument("--worker-budget", type=float, default=240, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.check:
        import importlib
        for module in ["requests", "pdfplumber", "openpyxl", "matplotlib", "fontTools", "brotli", "bs4", "jupyter", "nbformat", "nbclient", "ipykernel"]:
            importlib.import_module(module)
        quarto = shutil.which("quarto") or "C:/Program Files/Quarto/bin/quarto.exe"
        require(Path(quarto).exists(), "Quarto 사전 준비 필요")
        for name in ["assets/serongi.svg", "slides/assets/fonts/PretendardVariable.woff2", "demo/cases/d-grade7/raw.pdf", "demo/cases/d-grade7/SOURCE.md"]:
            require((ROOT / name).exists(), "필수 원본/자산 없음: " + name)
        print("사전 환경 확인 통과: Python 의존성·Quarto·원본 PDF·공용 로고·Pretendard")
        return
    if args.recheck:
        recheck(Path(args.recheck).resolve())
        return
    if args.rebuild:
        folder = Path(args.rebuild).resolve()
        state = json.loads((folder / "run-input.json").read_text(encoding="utf-8"))
        ROOT = Path(state["root"])
        args.agent, args.model = state["agent"], state["model"]
    if args.worker:
        worker(args, Path(args.worker).resolve())
        return
    require(re.fullmatch(r"[a-z0-9_-]+", args.agent) is not None, "에이전트명은 소문자 식별자 필요")
    started = datetime.fromisoformat(args.started_at.replace("Z", "+00:00")) if args.started_at else datetime.now(timezone.utc)
    require(started.tzinfo is not None, "시작 시각에 시간대 필요")
    elapsed = (datetime.now(timezone.utc) - started).total_seconds()
    require(0 <= elapsed < 260, "시작 시각 오류 또는 남은 실행 시간 부족")
    folder = folder if args.rebuild else ROOT / ("sejong-oneshot-" + args.agent + "-" + datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y%m%d-%H%M%S"))
    if not args.rebuild:
        folder.mkdir()  # Never reuse an existing result folder.
    timeout = min(260 - elapsed, 240)
    command = [sys.executable, str(Path(__file__).resolve()), "--worker", str(folder), "--agent", args.agent, "--model", args.model, "--worker-budget", str(timeout)]
    if args.evidence:
        command += ["--evidence", str(Path(args.evidence).resolve())]
    if args.rebuild:
        command += ["--rebuild", str(folder)]
    try:
        result = subprocess.run(command, timeout=timeout)
        require(result.returncode == 0, "생성·검증 미완료")
        timing = json.loads((folder / "timing.json").read_text(encoding="utf-8"))
        timing.update(total_seconds=round((datetime.now(timezone.utc) - started).total_seconds(), 3), scope="요청 수신부터" if args.started_at else "실행 명령부터")
        require(timing["total_seconds"] < 300, "5분 제한 초과; 완료 판정 금지")
        save(folder, "timing.json", json.dumps(timing, ensure_ascii=False, indent=2))
        print(f"완료: {folder}\n실측: {timing['total_seconds']:.2f}초 ({timing['scope']})", flush=True)
    except Exception as exc:
        save(folder, "timing.json", json.dumps({"status": "incomplete", "error": str(exc), "total_seconds": round((datetime.now(timezone.utc) - started).total_seconds(), 3)}, ensure_ascii=False, indent=2))
        raise


if __name__ == "__main__":
    main()
