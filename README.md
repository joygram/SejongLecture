# 세종대 AI 글쓰기 특강 (60분)

- 2026-11-05(목) 13:30–14:30 · 이론 30분 + 라이브 시연·따라하기 30분

## 구성
- `slides/` = Quarto revealjs 슬라이드, 발표자 노트·노출 목적·판단 질문 = 로컬 워크벤치
- `handout/prompts.html` = 학생 페이지 (QR = https://joygram.github.io/SejongLecture/handout/prompts.html, 생성 = python slides/workbench.py qr, PDF = python slides/workbench.py pdf)
- `handout/practice.md` = 학생 실습지
- `demo/README.md` = 같은 팀 리포트를 완성·공유하는 2부 시연 대본
- `demo/oneshot.py` = 준비된 수집·제작 코드; 강사 시연에서 사용 사실 공개, 실행 뒤 사람이 결과 검토
- `demo/report_workflow.py` + `demo/report-story.qmd` = 보관 CSV 재편집 예제, 원샷 신규 수집과 구분
- `demo/pipeline.py` + `demo/cases.json` = 수집 → 점검 → 사람 판정 → 시트·리포트
- `demo/cases/<사례>/` = raw 원본, data.csv, SOURCE.md, CHECK.md, DECISIONS.md, sheet.xlsx

## 실행
- `python demo/pipeline.py fetch all` → `inspect all` → 각 DECISIONS.md 작성 → `build all`
- `quarto render slides/sejong-ai-writing.qmd`
- 필요: Quarto, Python + pandas·matplotlib·openpyxl·pdfplumber·jupyter

## 슬라이드 제작·검수
- 워크벤치 = `slides/workbench/README.md`, 재사용 제작 프롬프트 = `slides/SLIDE_PROMPT.txt`.
- `python slides/workbench.py build` → `check` → `serve`.
- 청중용 HTML에는 발표자 노트 미포함, 발표자 노트는 로컬 워크벤치에서 확인.
