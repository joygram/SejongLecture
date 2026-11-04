"""Offline rehearsal copies. Original case decisions and reports are never edited."""
from pathlib import Path
import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
ARTIFACTS=ROOT/'slides/.workbench'
STATE=ARTIFACTS/'rehearsal-session.json'
CASE='d-grade7'


def copy_inputs(target):
    target.mkdir(parents=True,exist_ok=True)
    for name in ['pipeline.py','cases.json','report-exam.qmd']:
        shutil.copy2(HERE/name,target/name)
    case_dir=target/'cases'/CASE
    case_dir.mkdir(parents=True)
    for name in ['data.csv','SOURCE.md','CHECK.md','DECISIONS.md']:
        shutil.copy2(HERE/'cases'/CASE/name,case_dir/name)


def prepare():
    ARTIFACTS.mkdir(parents=True,exist_ok=True)
    session=Path(tempfile.mkdtemp(prefix='rehearsal-',dir=ARTIFACTS)).resolve()
    copy_inputs(session/'snapshot')
    STATE.write_text(json.dumps({'session':str(session)},ensure_ascii=False),encoding='utf-8')
    print(f'준비 완료: {session}\n원본 데이터·판정·완성본 유지. 다음 단계: pending → sat → eligible')


def run(mode):
    if not STATE.exists(): raise RuntimeError('먼저 python demo/rehearse.py prepare 실행 필요')
    session=Path(json.loads(STATE.read_text(encoding='utf-8'))['session']).resolve()
    if not session.is_relative_to(ARTIFACTS.resolve()) or not (session/'snapshot').is_dir():
        raise RuntimeError('격리 리허설 경로 확인 실패')
    target=Path(tempfile.mkdtemp(prefix=mode+'-',dir=session))
    shutil.copytree(session/'snapshot',target,dirs_exist_ok=True)
    decisions=target/'cases'/CASE/'DECISIONS.md'
    text=decisions.read_text(encoding='utf-8')
    value='' if mode=='pending' else ('응시인원' if mode=='sat' else '응시대상인원')
    text=re.sub(r'(## 경쟁률 분모\n.*?- 결정 =)[^\n]*',lambda m:m.group(1)+' '+value,text,count=1,flags=re.S)
    if mode=='eligible':
        text=text.replace('시험장에 오지 않은 사람은 실제 경쟁에 참여하지 않음','비교 시연에서는 응시대상 규모를 확인, 실제 응시 경쟁률과 구별')
    decisions.write_text(text,encoding='utf-8')
    outcome=subprocess.run([sys.executable,str(target/'pipeline.py'),'build',CASE],cwd=target)
    if mode=='pending':
        if outcome.returncode!=1 or (target/f'report-{CASE}.html').exists():
            raise RuntimeError('예상한 판정 누락 정지와 다른 결과')
        print('시연 확인: 판정 미입력으로 생성 중단. 다음 단계: python demo/rehearse.py sat')
    else:
        if outcome.returncode:raise RuntimeError(f'리허설 빌드 실패, 출력 확인: {target}')
        ratio='23.3:1' if mode=='sat' else '38.1:1'
        print(f'확인 기준: 총계 {ratio}\n완성본: {target / f"report-{CASE}.html"}')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('step',choices=['prepare','pending','sat','eligible'])
    args=parser.parse_args()
    try:
        if args.step=='prepare':prepare()
        else:run(args.step)
    except (RuntimeError,OSError) as exc:
        print(str(exc),file=sys.stderr);sys.exit(1)
