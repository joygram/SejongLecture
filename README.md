# 세종대 AI 글쓰기 특강 (60분)

- 2026-11-05(목) 13:30–14:30 · 이론 30분 + 라이브 시연·따라하기 30분

## 강의 내용 요약
- 목표 = 같은 팀 보고서를 메모 → 초안 → 표·차트 대조 → 퇴고 → 팀 채팅 초안까지 완성.
- 1부 · 이론 30분 = AI와 사람의 역할, 프롬프트 4요소(맥락·역할·제약·예시), 자료 기반 글쓰기, 환각·표절·내 목소리 잃기 점검.
- 2부 · 시연·따라하기 30분 = 메모로 서론 쓰기, 같은 숫자의 표·차트·문장 비교, 코딩 에이전트와 Quarto 보고서 제작 시연.
- 핵심 판단 = ‘응시인원이 많음’과 ‘인기가 높음’ 구분; 수치·출처 대조와 해석·최종 승인은 사람 몫.

## 슬라이드 보는 방법
- 온라인 = [강의 슬라이드](https://joygram.github.io/SejongLecture/); 첫 화면에서 슬라이드로 이동.
- 로컬 = 저장소 다운로드 후 [슬라이드 HTML](slides/sejong-ai-writing.html)을 브라우저로 열기; `slides/` 폴더 전체 유지.
- 이동 = 빈 화면 클릭으로 다음 장, Shift+클릭 또는 마우스 오른쪽 클릭으로 이전 장.
- PDF = [슬라이드 PDF](slides/sejong-ai-writing.pdf) 다운로드 후 복습·인쇄.
- 열람·기본 실습 = Python·Quarto 설치 불필요; 제작·재실행 환경은 아래 실행 항목 참고.

## 실습 시작
- 준비 = 평소 쓰는 AI 채팅 열기 → [학생용 프롬프트 카드](handout/prompts.html)를 브라우저로 열기.
- 온라인 카드 = [학생 페이지](https://joygram.github.io/SejongLecture/handout/prompts.html); 입력 원문 = [실습지](handout/practice.md).
- 진행 = 같은 채팅에 카드 1 → 카드 2 순서로 입력; 카드 3은 수업 뒤 이어서 실습.
- 기록 = AI 답에서 살릴 문장·바꿀 문장과 직접 확인한 숫자·출처 구분.

### 카드별 할 일
- 카드 1 · 서론 = 팀 메모로 첫 문단 생성 → 메모에 없는 사실 확인 → 살릴 문장·바꿀 문장 선택.
- 카드 2 · 데이터 = 제공된 세 분야 응시인원으로 세 문장·차트 A/B 요청 → 표·차트·문장 숫자 대조 → 강조할 관점 선택.
- 카드 3 · 퇴고 = 앞선 결과를 보고서 초안으로 묶기 → 근거 없는 주장 수정 → AI·사람의 작업과 사람 미확인 항목 기록.
- 마무리 · 공유 = 실습지의 마지막 요청으로 팀 채팅 3줄 초안 생성 → 결론·숫자·남은 확인 검토 → 실제 주소 확인 후 사람이 직접 공유.

### 강사 시연·추가 실습
- 강사 진행 = [시연 대본](demo/README.md); 코딩 에이전트·Quarto 구간은 강사 시연.
- 원샷 재현 = [학생용 요청문](demo/ONESHOT_PROMPT.md)과 [실행 워크플로](demo/ONESHOT_WORKFLOW.md) 확인 후 코딩 에이전트에서 실행; 매번 새 결과 폴더 생성.
- 생성 뒤 = 결과 폴더의 `NEXT_STEPS.md`에 따라 원자료·출처 확인 → 해석 결정 → 우리 글로 수정 → 재생성·재대조 → 사람 승인·공유.
- 도구별 활용 = [환경 안내](handout/tool-workflows.md), 문체 입력 = [스타일 템플릿](demo/REPORT_STYLE_TEMPLATE.txt).

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
