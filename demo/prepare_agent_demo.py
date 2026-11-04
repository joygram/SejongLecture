"""Prepare offline before/after reports and a disposable live editing copy."""
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parent.parent

def main():
    base = ROOT / 'slides/.workbench'
    base.mkdir(parents=True, exist_ok=True)
    target = Path(tempfile.mkdtemp(prefix='agent-demo-', dir=base))
    template = (ROOT / 'demo/report-story.qmd').read_text(encoding='utf-8-sig')
    quarto = shutil.which('quarto') or 'C:/Program Files/Quarto/bin/quarto.exe'
    for name, focus in [('before', '행정직'), ('after', '외무영사직')]:
        folder = target / name
        folder.mkdir()
        for source in ['data.csv', 'SOURCE.md']:
            shutil.copy2(ROOT / 'demo/cases/d-grade7' / source, folder / source)
        source = template.replace('FOCUS = "행정직"', f'FOCUS = "{focus}"')
        (folder / 'report.qmd').write_text(source, encoding='utf-8')
        subprocess.run([quarto, 'render', 'report.qmd'], cwd=folder, check=True)
    shutil.copytree(target / 'before', target / 'live')
    prompt = f'''{target / 'live/report.qmd'} 파일만 수정해줘.
FOCUS = "행정직"을 FOCUS = "외무영사직"으로 바꿔줘.
다른 코드·본문·수치·축·정렬·원자료는 수정하지 마.
그 폴더에서 "{quarto}" render report.qmd 를 실행해줘.
바꾼 한 줄과 생성된 report.html 경로를 보여줘.
실패하면 설치나 추가 수정 없이 오류를 알려주고 멈춰.
'''
    (target / 'LIVE_PROMPT.txt').write_text(prompt, encoding='utf-8')
    print(f'준비 폴더: {target}\n현장 입력: {target / "LIVE_PROMPT.txt"}\n시작 화면: {target / "live/report.html"}\n대체 화면: {target / "after/report.html"}')

if __name__ == '__main__':
    main()
