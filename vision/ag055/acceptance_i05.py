"""Run final AG-055 acceptance with external evidence and isolated browser fixture.

No training, migration or changes to existing datasets/models/user database. Servers
are loopback-only, refused if ports are occupied, and terminated on completion.
"""
import argparse
import hashlib
import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from .experimental import private


def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):
            h.update(block)
    return h.hexdigest()


def execute(args):
    repo=Path(__file__).resolve().parents[2]
    output=private(args.output); output.mkdir()
    env=os.environ.copy()
    env['PYTHONPATH']=os.pathsep.join(map(str,[repo,repo/'backend',repo/'backend/tests',repo/'backend/.venv/Lib/site-packages']))
    env['PYTHONIOENCODING']='utf-8'
    env['PYTHONUTF8']='1'  # Includes child-CLI decoding inside Windows tests.
    # The legacy real-image test writes only if its evidence is absent. Enable it
    # only when that immutable evidence already exists, and protect its hash.
    env.pop('AG055_REAL_RUN',None)
    protected=[repo/'backend/data/agroscan.db',args.i04/'uncertainty_policy.json',args.run/'manifest.json',
        args.run/'report.json',*sorted((args.run/'models').glob('*.json'))]
    if (args.run/'fastapi_real_evidence.json').is_file():
        env['AG055_REAL_RUN']=str(args.run)
        protected.append(args.run/'fastapi_real_evidence.json')
    if (args.run/'react_real_evidence.html').is_file():
        protected.append(args.run/'react_real_evidence.html')
    env['AG055_RENDER_EVIDENCE_OUTPUT']=str(output/'react_real_evidence.html')
    if args.pilot_run:
        env['AG055_PILOT117_RUN']=str(args.pilot_run.resolve())
    if args.v2_run:
        env['AG055_V2_RUN']=str(args.v2_run.resolve())
        protected.extend([args.v2_run/'manifest.json',args.v2_run/'report.json',*sorted((args.v2_run/'models').glob('*.json'))])
    before={str(p):digest(p) for p in protected}
    results={}
    def run(name,command,cwd=repo):
        print('Running '+name,flush=True)
        process=subprocess.run(command,cwd=cwd,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        raw=process.stdout.decode('utf-8',errors='replace')
        (output/f'{name}.log').write_text(raw,encoding='utf-8')
        count=re.search(r'Ran (\d+) tests',raw) or re.search(r'tests (\d+)',raw)
        results[name]={'exitCode':process.returncode,'tests':int(count[1]) if count else None,
            'skipped':re.findall(r'skipped[= ]+(\d+)',raw)}
        print(name+': '+json.dumps(results[name]),flush=True)
        return process.returncode
    npm=__import__('shutil').which('npm.cmd')
    if not npm:
        raise RuntimeError('npm.cmd not available')
    try:
        run('backend_tests',[sys.executable,'-m','unittest','discover','-s','backend/tests','-v'])
        # Optional legacy experiment dependencies belong only to the full vision
        # test process. Never substitute the original NumPy/Pillow/model runtime.
        original_path=env['PYTHONPATH']
        if args.vision_deps:
            env['PYTHONPATH']=original_path+os.pathsep+str(args.vision_deps.resolve())
        try:
            run('vision_tests',[sys.executable,'-m','unittest','discover','-s','vision/tests','-v'])
        finally:
            env['PYTHONPATH']=original_path
        run('frontend_tests',[npm,'test'],repo/'frontend')
        run('frontend_build',[npm,'run','build'],repo/'frontend')
        run('quality_lint',['node','node_modules/eslint/bin/eslint.js','src/features/quality','src/services/agroscanApi.ts'],repo/'frontend')
        for port in (18004,5174):
            with socket.socket() as probe:
                if probe.connect_ex(('127.0.0.1',port))==0:
                    raise RuntimeError(f'Port {port} occupied; refusing to disturb another process')
        env.update(AG055_REAL_RUN=str(args.run),AG055_FROZEN_POLICY=str(args.i04/'uncertainty_policy.json'),
            AG055_I04_EVIDENCE=str(output),AG055_TEST_PASSWORD='I05-local-fixture-only!',
            VITE_API_BASE_URL='http://127.0.0.1:18004',AG055_I05_AUDIT='1',
            AG055_PLAYWRIGHT_ROOT=str(args.playwright_root),AG055_CHROMIUM_PATH=str(args.chromium))
        servers=[]
        logs=[]
        try:
            for name,command,cwd in [
                ('api_server',[sys.executable,'-m','uvicorn','ag055_i04_app:app','--host','127.0.0.1','--port','18004'],repo),
                ('vite_server',['node','node_modules/vite/bin/vite.js','--host','127.0.0.1','--port','5174','--strictPort'],repo/'frontend')]:
                log=(output/f'{name}.log').open('wb'); logs.append(log)
                servers.append(subprocess.Popen(command,cwd=cwd,env=env,stdout=log,stderr=subprocess.STDOUT,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0))
            for url in ['http://127.0.0.1:18004/_ag055_test_instance','http://127.0.0.1:5174']:
                for _ in range(100):
                    if any(s.poll() is not None for s in servers):
                        raise RuntimeError('Isolated server exited; inspect server logs')
                    try:
                        with urllib.request.urlopen(url,timeout=1) as response:
                            if response.status==200:
                                break
                    except OSError:
                        time.sleep(.1)
                else:
                    raise RuntimeError('Isolated server startup timed out')
            run('browser_e2e',['node','frontend/tests/ag055-pilot117-e2e.mjs' if args.pilot_run else 'frontend/tests/ag055-i04-e2e.mjs'])
            if args.v2_run:
                run('browser_v2_e2e',['node','frontend/tests/ag055-v2-e2e.mjs'])
        finally:
            for server in servers:
                server.terminate()
            for server in servers:
                server.wait(timeout=15)
            for log in logs:
                log.close()
    finally:
        after={str(p):digest(p) for p in protected}
        summary={'commands':results,'protectedBefore':before,'protectedAfter':after,'protectedUnchanged':before==after,
            'runtime':sys.version,'output':str(output),'noTraining':True,'noMigration':True,
            'passed':bool(results) and all(r['exitCode']==0 for r in results.values()) and 'browser_e2e' in results and before==after}
        (output/'acceptance.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    if not summary['passed']:
        raise RuntimeError('Acceptance incomplete/failed; inspect logs')
    print('Acceptance PASSED: '+str(output),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',type=Path,required=True)
    parser.add_argument('--i04',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--playwright-root',type=Path,required=True)
    parser.add_argument('--chromium',type=Path,required=True)
    parser.add_argument('--vision-deps',type=Path,help='External optional sklearn/scipy dependencies for full vision tests only')
    parser.add_argument('--pilot-run',type=Path,help='Audited pilot117 workspace for its isolated real-photo E2E')
    parser.add_argument('--v2-run',type=Path,help='Frozen V2 workspace; real masked inference and reject/review E2E')
    execute(parser.parse_args())
