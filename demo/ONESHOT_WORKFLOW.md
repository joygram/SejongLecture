# 원샷 실행과 초안 이후 워크플로

## 적용
- 진입 = [프로젝트 룰](../AGENTS.md) → [학생용 원샷 프롬프트](ONESHOT_PROMPT.md) → [에이전트 전용 제작 규칙](ONESHOT_AGENT_RULES.md) → 이 실행 흐름
- 범위 = 매 실행 새 sejong-oneshot-에이전트명-날짜시간 폴더; 기존 산출물 수정 금지
- 별도 실습 = report_workflow.py는 보관 CSV 재편집 예제; 원샷 수집 경로로 사용 금지

## 5분 실행 순서
- 0–15초 = 요청 수신 UTC 시각 기록·이 규칙 한 번 읽기·`python demo/oneshot.py --check`; 설치·환경 탐색은 시연 전 완료
- 15–60초 = 경쟁률 보도자료·지원 동기 논문을 한 번에 검색하고 원문 열람; 확인한 URL·요약·열람 범위·조회일만 임시 evidence.json에 저장, 미확인은 그대로 기록
- 60–240초 = `python demo/oneshot.py --agent <실제 에이전트> --model "모델명 미확인" --started-at <요청수신UTC시각> --evidence <임시파일>`; 모델명은 환경에서 확인한 경우만 변경
- 240–300초 = 실행 로그·timing.json·CHECK.md·생성 HTML 확인 후 결과 보고; 수집→정리→표현→해석→점검 과정과 사람 후속 단계 공개
- 지연 통제 = HTTP 연결 3초/읽기 7초·재시도 없음·독립 요청 동시 수행·렌더 최대 100초·실행기 상한 240초; 300초 넘으면 미완료 판정

## 근거 전달과 재실행
- evidence.json = press·paper 각 1개 객체의 배열; 필드 = kind, title, url, summary, access, verified, checked_at(한국 날짜), via(검색·원문 열람 방법)
- 직접 읽은 원문만 verified=true; 논문 초록 열람을 본문 열람으로 표기 금지; 확인 못한 수치·결과를 summary에 쓰지 않음
- 실행기 기본 HTTP 경로도 제공; 검색 도구로 원문을 확인한 경우 --evidence로 전달, 동일 페이지 재수집 생략
- 코드 재사용 = 원본 추출·엑셀·차트·보고서·검증 로직만 재사용; 기존 data.csv·완성 보고서 재활용 금지
- 재생성 = 결과 폴더 README 참고; --rebuild는 원본 PDF를 다시 추출하고 AI 초안 재생성, 사람 수정 원고만 다시 만들 때는 Quarto 렌더만 실행

## 세롱이 실행
1. 수집 → 공식 게시 페이지·PDF 신규 확보; 실패 시 제공 보관본 확인; 연도 불일치·미확보는 수치 생성 중단
2. 추출·정리 → raw 원본·페이지별 원문·data.csv 보존; 결측 유지; 직군 계만 비교; 총계 중복 제외
3. 엑셀 → 출처·추출원문·정리데이터·비교표, 필요 시 인기기준; 동일 비교표를 참조하는 편집 가능 차트 A·B
4. 해석 → 응시인원·선발 대비 순위 비교; 경쟁률 보도자료 원문·지원 동기 연구 확인; 초록·본문 열람 범위 공개
5. 제작 → Quarto 원고·HTML·PNG·SCSS·팀 채팅 초안·재실행 코드·README·출처·점검·NEXT_STEPS 생성

## 시각·기록 기준
- 로고 = [공용 세롱이 SVG](../assets/serongi.svg); 결과 원고는 ../assets/serongi.svg 참조; HTML 내장
- 제작 표기 = 보고서 최상단 40px 얼굴 + 세롱이 (실제 에이전트 / 확인한 모델명) - AI 글쓰기 도우미 by 한국 시각 생성 날짜시간; 생성 줄과 합침
- 테마 = [슬라이드 SCSS](../slides/sejong-slides.scss)의 색·[Pretendard](../slides/assets/fonts/PretendardVariable.woff2); 다크 색 정의·HTML 폰트 내장
- 기록 = 단계 / 세롱이 / 사람; 출처의 사람이 제공 / 세롱이가 찾음 구분; 맨 아래 윤리 가이드

## 완료 점검
- 원본 대조 = 추출 행·숫자·결측·페이지, 직군 계·총계 합계, 기준별 비율·순위
- 엑셀 = openpyxl 재열기로 참조·축·정렬·강조색 확인; Excel·LibreOffice 탐색·설치 금지; 화면은 사람 확인
- HTML = 실제 Quarto 렌더, 공용 로고·폰트·PNG 내장, 차트 일치, 다크 모드·가용한 브라우저 화면 점검
- 링크 = NEXT_STEPS의 로컬 대상·보고서 절 앵커 존재 확인; 외부 자료 접근 상태 기록
- 결과 = CHECK.md에 세롱이 점검·사람 미확인 구분; 실제 전송 없음

## 사람이 이어갈 단계
1. 확인 → 원본 PDF·data.csv·report.xlsx·출처표·SOURCE.md·CHECK.md 열기; 숫자·화면·이용 조건·논문 본문 검토
2. 판단 → report.qmd에서 인기의 기준·차트 A/B·미확인 항목 처리 결정; NEXT_STEPS.md에 기록
3. 우리 글로 수정 → report.qmd 첫 문장·관심·해석 수정; NEXT_STEPS.md에 고친 문장·이유 기록
4. 다시 생성 → `python scripts/oneshot.py --recheck .`; 원본 재추출·재렌더·HTML·엑셀 재대조
5. 공유 → team-chat.txt 수정; 사람 확인자·날짜 갱신; 실제 공유 주소 확인 후 사람이 승인·직접 전송

## 단계마다 나오는 것
- 확인·판단·수정·공유 → NEXT_STEPS.md "우리 기록" 칸
- 수정 → RECHECK.md의 AI 초안 대비 바뀐 문장; 기준 = drafts/ 보관본
- 다시 생성 → 새 report.html·RECHECK.md(숫자 대조·단계 체크·남은 미확인)
- 재대조 불일치 → RECHECK.md에 기록·종료 코드 실패; 통과로 보고 금지

## 다음 단계 연결
- NEXT_STEPS.md = 위 다섯 단계의 실행별 체크리스트; 모든 항목에 실제 파일·출처·절 링크·나오는 것
- report.qmd = 작성 과정 기록 다음에 NEXT_STEPS.md include; 출처·윤리 가이드가 뒤따름
- 링크 형식 = 결과 폴더 기준 상대경로; 보고서 절은 고정 앵커; 클릭 대상과 실행 명령 구별
- 공유 = HTML 자체는 이미지·폰트 내장; 별도 파일 링크는 폴더 구조 유지 필요; 로컬 경로를 팀 공유 주소로 대체 금지
