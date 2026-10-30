"""Repeatable pinned-dependency, regression and isolated native checks."""
from pathlib import Path
import argparse
import importlib.metadata
import os
import subprocess
import sys
import re
import time
from concurrent.futures import ThreadPoolExecutor
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from cargo_track import __version__


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--skip-native',action='store_true')
    parser.add_argument('--jobs',type=int,choices=range(1,9),default=1,
                        help='Use isolated module processes when greater than one')
    args=parser.parse_args()
    for filename in ('requirements.txt','requirements-build.txt'):
        for line in (ROOT/filename).read_text(encoding='utf-8').splitlines():
            if '==' in line:
                name,version=line.strip().split('==')
                if importlib.metadata.version(name)!=version:raise RuntimeError('Dependency differs from its pin: '+name)
    print('Pinned dependencies: PASS',flush=True)
    suffix='-isolated' if args.jobs>1 else ''
    out=ROOT/f'output/checks-{__version__}{suffix}';out.mkdir(parents=True,exist_ok=True)
    temporary=ROOT/'.tmp-build';temporary.mkdir(exist_ok=True)
    env={**os.environ,'TMP':str(temporary),'TEMP':str(temporary),'PYTHONPATH':os.pathsep.join((str(ROOT/'src'),str(ROOT/'tests'))),
         'QT_QPA_PLATFORM':'offscreen','PYTHONIOENCODING':'utf-8'}
    commands=[]
    if args.jobs>1:
        started=time.monotonic()
        modules=sorted(p.stem for p in (ROOT/'tests').glob('test_*.py'))
        def run_module(name):
            path=out/(name+'.log')
            with path.open('w',encoding='utf-8') as log:
                result=subprocess.run([sys.executable,'-m','unittest',name,'-v'],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
            return name,result.returncode,path.read_text(encoding='utf-8')
        with ThreadPoolExecutor(max_workers=args.jobs) as executor:results=list(executor.map(run_module,modules))
        count=skipped=0;failed=[]
        with (out/'full-tests.log').open('w',encoding='utf-8') as log:
            log.write(f'Process-isolated unittest modules; jobs={args.jobs}\n')
            for name,code,value in results:
                log.write('\nModule: '+name+'\n'+value+'\n')
                match=re.search(r'Ran (\d+) tests',value)
                skip=re.search(r'OK \(skipped=(\d+)\)',value)
                if match:count+=int(match[1])
                if skip:skipped+=int(skip[1])
                if code or not match:failed.append(name)
            summary=f'Ran {count} tests in {time.monotonic()-started:.3f}s\n\n'
            summary+=('FAILED modules: '+', '.join(failed) if failed else 'OK'+(f' (skipped={skipped})' if skipped else ''))
            log.write(summary+'\n')
        print(summary,flush=True)
        if failed:raise RuntimeError('Regression modules failed; see '+str(out))
    else:commands.append(('full-tests.log',['-m','unittest','discover','-s',str(ROOT/'tests'),'-v']))
    if not args.skip_native:commands.append(('native.log',[str(ROOT/'tools/verify_workspace_headers.py')]))
    for name,arguments in commands:
        path=out/name
        with path.open('w',encoding='utf-8') as log:
            result=subprocess.run([sys.executable,*arguments],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
        print('\n'.join(path.read_text(encoding='utf-8').splitlines()[-5:]),flush=True)
        if result.returncode:raise RuntimeError('Check failed; full output: '+str(path))
    print('Verification logs: '+str(out))


if __name__=='__main__':main()
