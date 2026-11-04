"""Build a simple editable report and team-chat draft from the existing source data."""
from pathlib import Path
import csv
import shutil
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parent.parent
SOURCE=ROOT/'demo/cases/d-grade7'

def main():
    artifact_dir=ROOT/'slides/.workbench'
    artifact_dir.mkdir(parents=True,exist_ok=True)
    target=Path(tempfile.mkdtemp(prefix='team-report-',dir=artifact_dir))
    shutil.copy2(SOURCE/'data.csv',target/'data.csv')
    shutil.copy2(SOURCE/'SOURCE.md',target/'SOURCE.md')
    template=(ROOT/'demo/report-story.qmd').read_text(encoding='utf-8-sig')
    (target/'report.qmd').write_text(template,encoding='utf-8')
    with (target/'data.csv').open(encoding='utf-8-sig',newline='') as handle:
        rows=[r for r in csv.DictReader(handle) if r['level']=='직군 계']
    largest=max(rows,key=lambda r:float(r['sat']))
    message=(f"리포트랑 그래프 고쳐서 올렸어. 세 분야 중 {largest['group']}에서 시험을 본 사람이 가장 많았어.\n"
             "표랑 그림 숫자는 맞췄고, 자료로 확인 안 된 '인기가 높다'는 말은 뺐어. 첫 문단도 우리 질문부터 시작하게 고쳤어.\n"
             "읽어보고 우리 팀이 더 궁금한 점이나 덧붙일 내용이 있으면 알려줘!\n")
    (target/'team-chat.txt').write_text(message,encoding='utf-8')
    quarto=shutil.which('quarto') or str(Path('C:/Program Files/Quarto/bin/quarto.exe'))
    subprocess.run([quarto,'render','report.qmd'],cwd=target,check=True)
    print(f'완성 리포트: {target / "report.html"}\n다시 고칠 원본: {target / "report.qmd"}\n팀 채팅 요약 예문: {target / "team-chat.txt"}\n실제 메시지는 전송하지 않음.')

if __name__=='__main__': main()
