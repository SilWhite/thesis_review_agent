"""Restart only the authorized thesis web process, leaving the model untouched."""
from pathlib import Path
import os,signal,subprocess,time,urllib.request,json
live=Path('/data01/amax/thesis_review_agent'); stopped=[]
for proc in Path('/proc').iterdir():
 if not proc.name.isdigit():continue
 try:args=(proc/'cmdline').read_bytes().decode().split('\0')
 except (OSError,UnicodeError):continue
 if any(Path(a).name=='uvicorn' for a in args) and '--port' in args and args[args.index('--port')+1]=='8088':
  os.kill(int(proc.name),signal.SIGTERM);stopped.append(int(proc.name))
for _ in range(20):
 if not any(Path('/proc',str(pid)).exists() for pid in stopped):break
 time.sleep(.5)
log=(live/'logs/agent.log').open('ab')
subprocess.Popen(['bash',str(live/'scripts/start_agent.sh')],cwd=live,stdout=log,stderr=log,stdin=subprocess.DEVNULL,start_new_session=True)
for _ in range(30):
 try:
  with urllib.request.urlopen('http://127.0.0.1:8088/api/v1/jobs',timeout=2) as response:
   if response.status==200:print(json.dumps({'stopped_web_pids':stopped,'health':'HTTP 200'}));break
 except Exception:time.sleep(.5)
else:raise SystemExit('Web health failed after restart')
