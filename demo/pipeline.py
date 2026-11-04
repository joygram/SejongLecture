import csv
import io
import json
import re
import shutil
import subprocess
import sys
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

HERE = Path(__file__).parent
CASES = json.loads((HERE / "cases.json").read_text(encoding="utf-8"))
PORTAL = "https://www.data.go.kr"
AGENT = {"User-Agent": "Mozilla/5.0"}
CERT_COLUMNS = {
    "종목명": "item", "년도": "year", "성별": "sex",
    "필기시험접수": "written_applied", "필기시험응시": "written_sat", "필기시험합격": "written_passed",
    "실기시험접수": "practical_applied", "실기시험응시": "practical_sat", "실기시험합격": "practical_passed",
    "자격취득자현황(명)": "certified",
}
CERT_COUNTS = list(CERT_COLUMNS.values())[3:]
EXAM_COLUMNS = ["level", "group", "unit", "track", "planned", "eligible", "sat", "eligible_raw", "sat_raw"]
SMALL_CERT = 500
SMALL_EXAM = 2
DECISIONS = {
    "certs": {
        "분모": ["응시", "접수"],
        "집계 단위": ["종목 행만", "분야 행만"],
        "포함 종목": ["전부", "일부"],
        "작은 표본": ["포함·인원 표시", "제외", "비율 쓰지 않음"],
        "성별": ["본문", "부록", "쓰지 않음"],
        "가장 어려운 시험": ["필기 기준으로 씀", "실기 기준으로 씀", "쓰지 않음"],
    },
    "exam": {
        "경쟁률 분모": ["응시인원", "응시대상인원"],
        "집계 단위": ["모집단위", "직군 계", "총계만"],
        "'-' 칸": ["0으로 읽음", "미공개로 두고 계산 제외"],
        "구분모집": ["일반·장애인 나눠서", "합쳐서", "일반만"],
        "선발 1–2명 단위": ["경쟁률 표시", "표시하되 순위에서 제외", "쓰지 않음"],
        "'경쟁이 가장 센 직렬'": ["쓴다", "쓰지 않음"],
    },
}


def folder(case):
    seat = HERE / "cases" / case
    seat.mkdir(parents=True, exist_ok=True)
    return seat


def portal_file(dataset, seat):
    page = f"{PORTAL}/data/{dataset}/fileData.do"
    html = urllib.request.urlopen(urllib.request.Request(page, headers=AGENT), timeout=30).read().decode("utf-8", "replace")
    title = re.search(r"<title>([^|<]+)", html).group(1).strip()
    detail = re.search(r"fn_fileDataDown\('" + dataset + r"', '(uddi:[^']+)'", html).group(1)
    asked = urllib.parse.urlencode({
        "publicDataDetailPk": detail, "publicDataPk": dataset, "atchFileId": "",
        "fileDetailSn": "1", "publicDataTyCode": "PR0051",
    }).encode()
    found = json.loads(urllib.request.urlopen(urllib.request.Request(
        f"{PORTAL}/tcs/dss/selectFileDataDownload.do", data=asked,
        headers={**AGENT, "X-Requested-With": "XMLHttpRequest", "Referer": page}), timeout=30).read())
    if found.get("status") is not True:
        raise SystemExit(f"{dataset} 내려받기 거절: {found}")
    raw = urllib.request.urlopen(urllib.request.Request(
        f"{PORTAL}/cmm/cmm/fileDownload.do?atchFileId={found['atchFileId']}&fileDetailSn={found['fileDetailSn']}",
        headers=AGENT), timeout=60).read()
    kind = "pdf" if raw.startswith(b"%PDF") else "hwpx" if b"hwp+zip" in raw[:200] else "csv"
    (seat / f"raw.{kind}").write_bytes(raw)
    return page, title, kind, raw


def decode_csv(raw):
    for encoding in ("utf-8-sig", "cp949"):
        try:
            return encoding, list(csv.DictReader(io.StringIO(raw.decode(encoding))))
        except UnicodeDecodeError:
            continue
    raise SystemExit("CSV 인코딩을 읽지 못함")


def write_rows(path, header, rows):
    with open(path, "w", encoding="utf-8", newline="") as out:
        writer = csv.writer(out)
        writer.writerow(header)
        writer.writerows(rows)


def write_source(seat, spec, page, title, note_lines):
    lines = [f"# 출처 — {spec['title']}", "", f"- 자료 = {title} ({page})", f"- 조회일 = {date.today().isoformat()}"]
    (seat / "SOURCE.md").write_text("\n".join(lines + note_lines) + "\n", encoding="utf-8")


def field_items(rows, field):
    names = list(dict.fromkeys(row["종목명"] for row in rows))
    if field not in names:
        raise SystemExit(f"{field} 행이 원본에 없음")
    items = []
    for name in names[names.index(field) + 1:]:
        if name.endswith("분야"):
            break
        items.append(name)
    return items


def fetch_certs(case, spec, seat):
    page, title, kind, raw = portal_file(spec["dataset"], seat)
    encoding, rows = decode_csv(raw)
    items = field_items(rows, spec["field"])
    kept = [row for row in rows if row["종목명"] in [spec["field"], *items]]
    write_rows(seat / "data.csv", CERT_COLUMNS.values(), [[row[name] for name in CERT_COLUMNS] for row in kept])
    years = sorted({row["년도"] for row in kept})
    write_source(seat, spec, page, title, [
        f"- 원본 = raw.csv ({encoding}, 가공 전)",
        f"- 뽑은 행 = {spec['field']} 행 + 그 아래 종목 {', '.join(items)}",
        f"- 연도 = {years[0]}–{years[-1]}",
    ])
    print(f"[{case}] 수집 {len(kept)}행 · 종목 {len(items)}개 · {years[0]}–{years[-1]} → data.csv, SOURCE.md")


def number(cell):
    text = (cell or "").replace(",", "").strip()
    return "" if text in ("", "-") else int(text)


def fetch_exam(case, spec, seat):
    import pdfplumber

    page, title, kind, _ = portal_file(spec["dataset"], seat)
    if kind != "pdf":
        raise SystemExit(f"{spec['dataset']} 가 PDF가 아님 ({kind})")
    rows, group = [], ""
    with pdfplumber.open(seat / "raw.pdf") as pdf:
        tables = [row for sheet in pdf.pages for table in sheet.extract_tables() for row in table]
    for cells in tables:
        name = (cells[0] or "").strip()
        if name in ("", "모집단위"):
            continue
        level = "총계" if name == "총계" else "직군 계" if name.endswith(" 계") else "모집단위"
        if level == "직군 계":
            group = name.removesuffix(" 계")
        track = "장애인" if "장애인" in name else "일반"
        rows.append([level, "" if level == "총계" else group, name, track,
                     number(cells[1]), number(cells[2]), number(cells[3]), cells[2], cells[3]])
    write_rows(seat / "data.csv", EXAM_COLUMNS, rows)
    write_source(seat, spec, page, title, [
        "- 원본 = raw.pdf (공문서 표, 가공 전)",
        "- 꺼낸 방법 = pdfplumber 표 추출. 쉼표 제거, '-'는 빈칸으로 두고 원문은 *_raw 열에 보존",
        f"- 꺼낸 행 = {len(rows)} (총계·직군 계·모집단위 섞임)",
    ])
    print(f"[{case}] PDF 표 추출 {len(rows)}행 → data.csv, SOURCE.md")


def read_csv(case):
    with open(folder(case) / "data.csv", encoding="utf-8") as source:
        return list(csv.DictReader(source))


def rate(part, whole):
    return part / whole * 100 if whole else float("nan")


def inspect_certs(case, spec):
    rows = read_csv(case)
    for row in rows:
        for name in CERT_COUNTS:
            row[name] = int(row[name])
    field = spec["field"]
    total = [row for row in rows if row["sex"] == "남녀합산"]
    items = [row for row in total if row["item"] != field]
    names = list(dict.fromkeys(row["item"] for row in items))
    last = max(row["year"] for row in rows)
    latest = {row["item"]: row for row in items if row["year"] == last}
    found = []
    field_rows = {row["year"]: row for row in total if row["item"] == field}
    if all(field_rows[year][name] == sum(row[name] for row in items if row["year"] == year)
           for year in field_rows for name in CERT_COUNTS):
        found.append(("집계 단위", f"{field} 행 = 종목 {len(names)}개의 합 (모든 연도·열). 함께 더하면 두 배",
                      "보고 싶은 것이 분야 전체인가, 종목 간 차이인가?"))
    absent = [100 - rate(row["written_sat"], row["written_applied"]) for row in items if row["written_applied"]]
    found.append(("분모", f"필기 결시율 {min(absent):.1f}–{max(absent):.1f}%. 접수로 나누면 결시자도 불합격으로 셈",
                  "시험을 치르지 않은 사람을 '떨어진 사람'으로 볼 것인가?"))
    small = [f"{name} 실기 응시 {row['practical_sat']:,}명" for name, row in latest.items() if row["practical_sat"] < SMALL_CERT]
    if small:
        found.append(("작은 표본", f"{last}년 " + ", ".join(small) + f" (기준 {SMALL_CERT}명 미만)",
                      "몇 명이 바뀌면 비율이 얼마나 흔들리는가? 그 비율을 문장에 써도 되는가?"))
    mismatch = [f"{row['item']} {row['year']} {row['sex']}: 실기 합격 {row['practical_passed']:,} ≠ 취득 {row['certified']:,}"
                for row in rows if row["practical_passed"] != row["certified"]]
    if mismatch:
        found.append(("자료 안 불일치", "; ".join(mismatch[:3]) + (f" 외 {len(mismatch) - 3}건" if len(mismatch) > 3 else ""),
                      "어느 숫자를 쓰고, 차이를 어디에 밝힐 것인가?"))
    found.append(("포함 종목", f"묶여 있는 종목: {', '.join(names)}",
                  "이 묶음이 내가 말하려는 대상과 같은가? 성격이 다른 종목이 섞였나?"))
    found.append(("성별", "남자 행 없음 → 남자 = 남녀합산 − 여자로 만들어야 함",
                  "이 자료에 원인을 설명할 정보(전공·경력)가 있는가? 차이를 쓰면 어떻게 읽히는가?"))
    written = {name: rate(row["written_passed"], row["written_sat"]) for name, row in latest.items() if row["written_sat"]}
    practical = {name: rate(row["practical_passed"], row["practical_sat"]) for name, row in latest.items() if row["practical_sat"]}
    hardest_w, hardest_p = min(written, key=written.get), min(practical, key=practical.get)
    found.append(("가장 어려운 시험",
                  f"{last}년 필기 최저 {hardest_w} {written[hardest_w]:.1f}% · 실기 최저 {hardest_p} {practical[hardest_p]:.1f}%",
                  "'어렵다'를 무엇으로 정의하는가? 기준을 바꾸면 답이 바뀌는가?"))
    return found


def as_int(value):
    return int(value) if value not in ("", None) else None


def inspect_exam(case, spec):
    rows = read_csv(case)
    for row in rows:
        for name in ("planned", "eligible", "sat"):
            row[name] = as_int(row[name])
    units = [row for row in rows if row["level"] == "모집단위"]
    groups = [row for row in rows if row["level"] == "직군 계"]
    total = next(row for row in rows if row["level"] == "총계")
    found = []

    checks = []
    for group in groups:
        members = [row for row in units if row["group"] == group["group"]]
        for name in ("planned", "eligible", "sat"):
            summed = sum(row[name] or 0 for row in members)
            checks.append((group["unit"], name, summed, group[name]))
    for name in ("planned", "eligible", "sat"):
        checks.append(("총계", name, sum(row[name] or 0 for row in groups), total[name]))
    broken = [f"{where} {name}: 더한 값 {summed:,} ≠ 표 {shown:,}" for where, name, summed, shown in checks if summed != shown]
    found.append(("추출 검증", "모든 계·총계가 모집단위 합과 일치 (PDF 추출 성공)" if not broken else "; ".join(broken),
                  "꺼낸 숫자가 원문과 같은지 무엇으로 확인했는가?"))
    found.append(("집계 단위", f"총계 1행 + 직군 계 {len(groups)}행 + 모집단위 {len(units)}행이 한 표에 섞임. 다 더하면 세 번 셈",
                  "말하려는 단위가 직렬인가, 직군인가, 전체인가?"))
    absent = 100 - rate(total["sat"], total["eligible"])
    found.append(("경쟁률 분모", f"응시대상 {total['eligible']:,} 중 응시 {total['sat']:,} (결시 {absent:.1f}%). "
                  f"총 경쟁률 {total['eligible'] / total['planned']:.1f}:1 vs {total['sat'] / total['planned']:.1f}:1",
                  "원서만 낸 사람까지 '경쟁자'로 볼 것인가?"))
    dashes = [f"{row['unit']} (응시대상 '{row['eligible_raw']}', 응시 '{row['sat_raw']}')"
              for row in units if row["eligible"] is None or row["sat"] is None]
    found.append(("'-' 칸", "; ".join(dashes), "'-'는 0명인가, 공개하지 않은 것인가? 원문 각주를 확인했는가?"))
    disabled = [row for row in units if row["track"] == "장애인"]
    found.append(("구분모집", f"장애인 구분모집 {len(disabled)}개 단위, 선발 {sum(row['planned'] for row in disabled)}명",
                  "구분모집을 둔 취지를 고려하면 일반과 합쳐 경쟁률을 내도 되는가?"))
    tiny = [row for row in units if row["planned"] <= SMALL_EXAM and row["sat"]]
    top = max(tiny, key=lambda row: row["sat"] / row["planned"])
    found.append(("선발 1–2명 단위", f"{len(tiny)}개 단위. 예: {top['unit']} 선발 {top['planned']}명에 응시 {top['sat']}명 "
                  f"({top['sat'] / top['planned']:.0f}:1)", "한두 명을 뽑는 자리의 경쟁률을 다른 직렬과 나란히 둘 수 있는가?"))
    prefixes = {}
    for row in units:
        head = row["unit"].split("(")[0]
        prefixes.setdefault(head.removesuffix("직"), set()).add(head)
    spelled = [" / ".join(sorted(names)) for names in prefixes.values() if len(names) > 1]
    if spelled:
        found.append(("원문 표기", "같은 직렬이 다르게 적힘: " + "; ".join(spelled), "원문을 고쳐 적을 것인가, 그대로 두고 밝힐 것인가?"))
    rated = [row for row in units if row["sat"] and row["planned"] > SMALL_EXAM]
    fiercest = max(rated, key=lambda row: row["sat"] / row["planned"])
    found.append(("'경쟁이 가장 센 직렬'", f"선발 3명 이상 중 최고: {fiercest['unit']} {fiercest['sat'] / fiercest['planned']:.1f}:1 (응시 기준)",
                  "이 문장이 수험생에게 어떻게 읽히는가? 기준을 바꾸면 순위가 바뀌는가?"))
    return found


def fetch(case):
    spec = CASES[case]
    (fetch_exam if spec["kind"] == "exam" else fetch_certs)(case, spec, folder(case))


def inspect(case):
    spec, seat = CASES[case], folder(case)
    found = (inspect_exam if spec["kind"] == "exam" else inspect_certs)(case, spec)
    lines = [f"# 자동 점검 — {spec['title']}", "", "| 판단할 자리 | 데이터에서 보인 것 | 사람이 답할 질문 |", "| --- | --- | --- |"]
    lines += [f"| {key} | {seen} | {question} |" for key, seen, question in found]
    (seat / "CHECK.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    decisions = seat / "DECISIONS.md"
    if not decisions.exists():
        template = [f"# 사람의 판정 — {spec['title']}", "", "- 결정 칸에 선택지 하나를 그대로 적고, 근거를 한 줄로 적는다", ""]
        for key, options in DECISIONS[spec["kind"]].items():
            template += [f"## {key}", f"- 선택지 = {' / '.join(options)}", "- 결정 = ", "- 근거 = ", ""]
        decisions.write_text("\n".join(template), encoding="utf-8")
    print(f"[{case}] 점검 {len(found)}건 → CHECK.md. 판정 → DECISIONS.md")
    for key, seen, _ in found:
        print(f"  · {key}: {seen}")


def read_decisions(case):
    kind = CASES[case]["kind"]
    text = (folder(case) / "DECISIONS.md").read_text(encoding="utf-8")
    blocks = {block.split("\n", 1)[0].strip(): block for block in text.split("\n## ")[1:]}
    chosen, missing = {}, []
    for key, options in DECISIONS[kind].items():
        block = blocks.get(key, "")
        picked = re.search(r"- 결정 = (.*)", block)
        reason = re.search(r"- 근거 = (.*)", block)
        value = picked.group(1).strip() if picked else ""
        why = reason.group(1).strip() if reason else ""
        if value not in options or not why:
            missing.append(f"{key} (선택지: {' / '.join(options)})")
            continue
        chosen[key] = {"결정": value, "근거": why}
    return chosen, missing


def styled_head(sheet):
    from openpyxl.styles import Font, PatternFill

    for cell in sheet[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="17324D")


def exam_sheet(case, book):
    from openpyxl.chart import BarChart, Reference

    sheet = book.active
    sheet.title = "모집단위"
    sheet.append(["직군", "모집단위", "구분", "선발예정", "응시대상", "응시", "경쟁률(응시)", "경쟁률(응시대상)", "결시율"])
    units = [row for row in read_csv(case) if row["level"] == "모집단위"]
    for line, row in enumerate(units, start=2):
        sheet.append([row["group"], row["unit"], row["track"], as_int(row["planned"]), as_int(row["eligible"]), as_int(row["sat"])])
        sheet[f"G{line}"] = f'=IF(F{line}="","",F{line}/D{line})'
        sheet[f"H{line}"] = f'=IF(E{line}="","",E{line}/D{line})'
        sheet[f"I{line}"] = f'=IF(OR(E{line}="",F{line}=""),"",1-F{line}/E{line})'
        sheet[f"G{line}"].number_format = sheet[f"H{line}"].number_format = "0.0"
        sheet[f"I{line}"].number_format = "0.0%"
    last = len(units) + 1
    sheet[f"A{last + 1}"] = "합계"
    for column in "DEF":
        sheet[f"{column}{last + 1}"] = f"=SUM({column}2:{column}{last})"
    sheet[f"G{last + 1}"] = f"=F{last + 1}/D{last + 1}"
    sheet[f"H{last + 1}"] = f"=E{last + 1}/D{last + 1}"
    sheet[f"A{last + 3}"] = "빈칸 = 원문 '-'. 0으로 바꾸지 않음. 경쟁률 = 인원 ÷ 선발예정"
    chart = BarChart()
    chart.type = "bar"
    chart.title = "모집단위별 경쟁률 (응시 기준)"
    chart.add_data(Reference(sheet, min_col=7, min_row=1, max_row=last), titles_from_data=True)
    chart.set_categories(Reference(sheet, min_col=2, min_row=2, max_row=last))
    chart.x_axis.scaling.min = 0
    chart.height, chart.width = 18, 16
    sheet.add_chart(chart, "K2")
    for column, width in zip("ABCDEFGHI", (12, 28, 8, 9, 9, 8, 12, 14, 8)):
        sheet.column_dimensions[column].width = width
    styled_head(sheet)


def certs_sheet(case, book):
    from openpyxl.chart import LineChart, Reference

    sheet = book.active
    sheet.title = "종목"
    sheet.append(["종목", "연도", "필기접수", "필기응시", "필기합격", "실기응시", "실기합격", "필기합격률", "실기합격률", "결시율"])
    field = CASES[case]["field"]
    rows = [row for row in read_csv(case) if row["sex"] == "남녀합산" and row["item"] != field]
    for line, row in enumerate(rows, start=2):
        sheet.append([row["item"], int(row["year"])] + [int(row[name]) for name in
                     ("written_applied", "written_sat", "written_passed", "practical_sat", "practical_passed")])
        sheet[f"H{line}"] = f'=IF(D{line}=0,"",E{line}/D{line})'
        sheet[f"I{line}"] = f'=IF(F{line}=0,"",G{line}/F{line})'
        sheet[f"J{line}"] = f'=IF(C{line}=0,"",1-D{line}/C{line})'
        for column in "HIJ":
            sheet[f"{column}{line}"].number_format = "0.0%"
    last = len(rows) + 1
    sheet[f"A{last + 2}"] = f"{field} 합계 행은 넣지 않음 (종목의 합 → 이중 집계). 합격률 분모 = 응시"
    chart = LineChart()
    chart.title = "연도별 실기 합격률"
    chart.add_data(Reference(sheet, min_col=9, min_row=1, max_row=last), titles_from_data=True)
    chart.y_axis.scaling.min = 0
    chart.height, chart.width = 8, 16
    sheet.add_chart(chart, "L2")
    styled_head(sheet)


def make_sheet(case):
    from openpyxl import Workbook

    book = Workbook()
    (exam_sheet if CASES[case]["kind"] == "exam" else certs_sheet)(case, book)
    book.save(folder(case) / "sheet.xlsx")


def quarto_bin():
    found = shutil.which("quarto")
    if found:
        return found
    installed = Path(r"C:\Program Files\Quarto\bin\quarto.exe")
    if installed.exists():
        return str(installed)
    raise SystemExit("quarto를 찾지 못함 — quarto.org에서 설치 후 다시 build")


def build(case):
    seat = folder(case)
    chosen, missing = read_decisions(case)
    if missing:
        print(f"[{case}] 빌드 멈춤 — 사람이 아직 판정하지 않은 자리:")
        for one in missing:
            print(f"  · {one}")
        raise SystemExit(1)
    (seat / "decisions.json").write_text(json.dumps(chosen, ensure_ascii=False, indent=2), encoding="utf-8")
    make_sheet(case)
    report = f"report-{CASES[case]['kind']}.qmd"
    (HERE / "cases" / "BUILDING").write_text(case, encoding="utf-8")
    subprocess.run([quarto_bin(), "render", report, "--output", f"report-{case}.html"], cwd=HERE, check=True)
    print(f"[{case}] 빌드 완료 → cases/{case}/sheet.xlsx, report-{case}.html")


def peek(case):
    import pdfplumber

    spec, seat = CASES[case], folder(case)
    page, title, kind, _ = portal_file(spec["dataset"], seat)
    print(f"[{case}] {title} → raw.{kind}")
    if kind != "pdf":
        return
    with pdfplumber.open(seat / "raw.pdf") as pdf:
        for number_, sheet in enumerate(pdf.pages, start=1):
            print(f"--- {number_}쪽")
            print(sheet.extract_text())


STEPS = {"peek": peek, "fetch": fetch, "inspect": inspect, "build": build}

if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] not in STEPS or (sys.argv[2] not in CASES and sys.argv[2] != "all"):
        raise SystemExit(f"사용법: python pipeline.py {{{'|'.join(STEPS)}}} {{{'|'.join(CASES)}|all}}")
    for name in CASES if sys.argv[2] == "all" else [sys.argv[2]]:
        STEPS[sys.argv[1]](name)
