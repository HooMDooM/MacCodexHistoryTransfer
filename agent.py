import hashlib,io,json,os,plistlib,re,shutil,signal,sqlite3,subprocess,sys,threading,time
from pathlib import Path

BASE=Path.home()/'Library/Application Support/Codex Transfer'
ROOT=Path.home()/'.codex'
NAMES={'sessions','archived_sessions','session_index.jsonl','history.jsonl','.codex-global-state.json','memories','memories_v2'}
DB=re.compile(r'^(state|thread_history|goals|memories|memories_v2)_\d+\.sqlite(?:-wal|-shm)?$')
BLOCK=1<<20
ARGS={}
STATE={}
STATE_LOCK=threading.Lock()

def selected(name):
    return name in NAMES or bool(DB.fullmatch(name))

def write_status():
    try:
        BASE.mkdir(parents=True,exist_ok=True,mode=0o700)
        data=dict(STATE,time=time.time())
        tmp=BASE/('status.json.'+str(os.getpid()))
        tmp.write_text(json.dumps(data,ensure_ascii=False))
        os.replace(tmp,BASE/'status.json')
    except OSError: pass

def status(phase,percent,message='',current=0,total=0):
    with STATE_LOCK:
        STATE.update(token=ARGS.get('token',''),role=ARGS.get('role',''),peer=ARGS.get('peer',''),phase=phase,percent=round(max(0,min(percent,100)),1),message=message,current=current,total=total)
        write_status()

def heartbeat():
    while True:
        time.sleep(2)
        with STATE_LOCK:
            if STATE: write_status()

def run(args,timeout=30):
    p=subprocess.run(args,capture_output=True,text=True,timeout=timeout)
    if p.returncode: raise RuntimeError(p.stderr.strip() or 'Команда завершилась с ошибкой: '+args[0])
    return p.stdout

def processes():
    rows=run(['/bin/ps','-axo','pid=,uid=,comm=']).splitlines()
    result=[]
    for row in rows:
        parts=row.strip().split(None,2)
        if len(parts)!=3: continue
        pid,uid,command=parts
        if int(uid)!=os.getuid() or int(pid)==os.getpid(): continue
        name=Path(command).name.lower()
        if name in ('codex','codex-cli','codex-app-server') or '/ChatGPT.app/Contents/' in command or '/Codex.app/Contents/' in command:
            result.append(int(pid))
    return result

def quiet():
    if processes(): raise RuntimeError('Codex снова запущен. Закройте его на обоих Mac и повторите перенос.')
    p=subprocess.run(['/usr/sbin/lsof','-t','+D',str(ROOT)],capture_output=True,text=True,timeout=300)
    if p.returncode not in (0,1): raise RuntimeError('Не удалось проверить открытые файлы Codex.')
    if p.stdout.strip(): raise RuntimeError('Файлы .codex используются другим процессом. Перенос остановлен.')

def application():
    for folder in [Path('/Applications'),Path.home()/'Applications']:
        for name in ['ChatGPT.app','Codex.app']:
            p=folder/name/'Contents/Info.plist'
            if p.exists():
                d=plistlib.loads(p.read_bytes())
                if d.get('CFBundleIdentifier')=='com.openai.codex':
                    return {'path':str(p.parent.parent),'version':d.get('CFBundleShortVersionString','')}
    raise RuntimeError('Приложение Codex не найдено в Applications.')

def probe():
    if not ROOT.is_dir() or ROOT.is_symlink(): raise RuntimeError('Ожидается обычная папка ~/.codex.')
    config=ROOT/'config.toml'
    if config.exists() and re.search(r'^\s*sqlite_home\s*=',config.read_text(),re.M):
        raise RuntimeError('Отдельный sqlite_home пока не поддерживается.')
    for key in ['CODEX_HOME','CODEX_SQLITE_HOME']:
        val=os.environ.get(key) or subprocess.run(['/bin/launchctl','getenv',key],capture_output=True,text=True).stdout.strip()
        if val and Path(val).expanduser()!=ROOT: raise RuntimeError('Нестандартное расположение '+key+' пока не поддерживается.')
    host=run(['/bin/hostname']).strip()
    name=subprocess.run(['/usr/sbin/scutil','--get','ComputerName'],capture_output=True,text=True).stdout.strip() or host
    return dict(home=str(Path.home()),app=application(),host=host,name=name,running=len(processes()))

def checked_token(token):
    if not re.fullmatch('[a-f0-9]{32}',token): raise RuntimeError('Некорректный идентификатор операции.')
    return BASE/'operations'/token

def incoming(token):
    checked_token(token)
    return ROOT.parent/('.codex-transfer-incoming-'+token)

def assert_lock(token):
    try: owner=(BASE/'lock/owner').read_text()
    except FileNotFoundError: owner=''
    if owner!=token: raise RuntimeError('Операция не владеет блокировкой.')

def acquire(token):
    BASE.mkdir(parents=True,exist_ok=True,mode=0o700)
    try: (BASE/'lock').mkdir(mode=0o700)
    except FileExistsError: raise RuntimeError('Уже идёт другой перенос. Дождитесь его завершения.')
    (BASE/'lock/owner').write_text(token)
    checked_token(token).mkdir(parents=True,mode=0o700)
    status('preparing',1)
    return {'ok':True}

def release(token,state,message):
    operation=checked_token(token)
    journal=operation/'journal.json'
    interrupted=journal.exists() and json.loads(journal.read_text()).get('status')=='prepared'
    if not interrupted:
        shutil.rmtree(incoming(token),ignore_errors=True)
        shutil.rmtree(operation,ignore_errors=True)
    status('done' if state=='done' else 'error',100 if state=='done' else STATE.get('percent',0),message)
    (BASE/'lock/owner').unlink(); (BASE/'lock').rmdir()
    return {'ok':True}

def stop():
    status('closing',3)
    application()
    script='tell application id "com.openai.codex" to quit'
    if processes():
        p=subprocess.run(['/usr/bin/osascript','-e',script],capture_output=True,text=True,timeout=40)
        if p.returncode: raise RuntimeError('macOS не разрешила закрыть Codex: '+p.stderr.strip())
    deadline=time.monotonic()+12
    while processes() and time.monotonic()<deadline: time.sleep(.5)
    for pid in processes():
        try: os.kill(pid,signal.SIGTERM)
        except ProcessLookupError: pass
    deadline=time.monotonic()+15
    while processes() and time.monotonic()<deadline: time.sleep(.5)
    quiet()
    status('closing',5)
    return {'ok':True}

def database_check(root):
    for p in root.glob('*.sqlite'):
        if not selected(p.name): continue
        db=sqlite3.connect(str(p),timeout=5)
        try:
            result=db.execute('PRAGMA quick_check').fetchall()
            if result!=[('ok',)]: raise RuntimeError('Повреждена база '+p.name)
        finally: db.close()

def unsupported(name):
    return RuntimeError('Ссылки и специальные файлы в истории не поддерживаются: '+name)

def manifest(root=None):
    root=root or ROOT
    files={};dirs=[]
    for child in sorted(root.iterdir()):
        if not selected(child.name): continue
        if child.is_symlink(): raise unsupported(child.name)
        if child.is_file():
            st=child.stat(); files[child.name]=[st.st_size,int(st.st_mtime)]
        elif child.is_dir():
            dirs.append(child.name)
            for folder,names,items in os.walk(child):
                base=Path(folder)
                for n in names:
                    p=base/n
                    if p.is_symlink(): raise unsupported(str(p.relative_to(root)))
                    dirs.append(str(p.relative_to(root)))
                for n in items:
                    p=base/n
                    if p.is_symlink() or not p.is_file(): raise unsupported(str(p.relative_to(root)))
                    st=p.stat(); files[str(p.relative_to(root))]=[st.st_size,int(st.st_mtime)]
        else: raise unsupported(child.name)
    return {'files':files,'dirs':dirs}

def checked_path(rel):
    p=Path(rel)
    if not isinstance(rel,str) or not p.parts or p.is_absolute() or '..' in p.parts or '\x00' in rel or not selected(p.parts[0]):
        raise RuntimeError('Недопустимый файл в архиве: '+str(rel))
    return p

def changed(source,dest):
    result=[]
    for path,info in source['files'].items():
        if dest['files'].get(path)!=info or DB.fullmatch(path): result.append(path)
    return result

def hashes(path,progress=None):
    result=[]
    with open(path,'rb') as f:
        while True:
            block=f.read(BLOCK)
            if not block: break
            result.append(hashlib.blake2b(block,digest_size=16).hexdigest())
            if progress: progress(len(block))
    return result

class Meter:
    def __init__(self,phase,start,width,total):
        self.phase=phase; self.start=start; self.width=width; self.total=max(int(total),1); self.count=0; self.last=0
    def __call__(self,size):
        self.count+=size
        now=time.monotonic()
        if now-self.last>.4:
            self.last=now
            status(self.phase,self.start+self.width*min(self.count/self.total,1),current=self.count,total=self.total)

def diff(dest):
    source=manifest()
    return {'paths':[p for p in changed(source,dest) if p in dest['files']]}

def blocks(paths):
    total=0
    for rel in paths:
        checked_path(rel)
        total+=(ROOT/rel).stat().st_size
    meter=Meter('comparing',5,5,total)
    status('comparing',5)
    return {'hashes':{rel:hashes(ROOT/rel,meter) for rel in paths}}

class Writer:
    def __init__(self,out):
        self.out=out; self.hash=hashlib.sha256(); self.count=0; self.meter=None
    def write(self,data):
        self.out.write(data); self.hash.update(data); self.count+=len(data)
        if self.meter: self.meter(len(data))
    def header(self,**record):
        self.write(json.dumps(record,ensure_ascii=False).encode()+b'\n')

def plan(source,dest,known):
    deletes=[p for p in dest['files'] if p not in source['files']]
    deletes+=sorted((p for p in dest['dirs'] if p not in source['dirs']),key=lambda p:-len(Path(p).parts))
    work=[];size=0
    for rel in changed(source,dest):
        size+=source['files'][rel][0] if rel in known else 0
    meter=Meter('comparing',10,5,size)
    for rel in changed(source,dest):
        length,mtime=source['files'][rel]
        mode=(ROOT/rel).stat().st_mode&0o777
        old=known.get(rel)
        if old is None:
            work.append(dict(op='file',path=rel,size=length,mtime=mtime,mode=mode,payload=length)); continue
        new=hashes(ROOT/rel,meter)
        parts=[[i,min(BLOCK,length-i*BLOCK)] for i,h in enumerate(new) if i>=len(old) or old[i]!=h]
        payload=sum(n for _,n in parts)
        if not parts and dest['files'][rel]==[length,mtime]: continue
        if payload>=length*.9 and length: work.append(dict(op='file',path=rel,size=length,mtime=mtime,mode=mode,payload=length))
        else: work.append(dict(op='patch',path=rel,size=length,mtime=mtime,mode=mode,blocks=parts,payload=payload))
    return deletes,work

def send(payload,out=None):
    quiet()
    out=out or sys.stdout.buffer
    status('comparing',10)
    source=manifest()
    deletes,work=plan(source,payload['manifest'],payload.get('hashes',{}))
    total=sum(w['payload'] for w in work)
    writer=Writer(out)
    writer.header(op='begin',total=total)
    writer.meter=Meter('sending',15,75,total+len(work)*200+len(deletes)*100)
    status('sending',15,total=total)
    for rel in deletes: writer.header(op='delete',path=rel)
    for rel in source['dirs']: writer.header(op='dir',path=rel)
    for item in work:
        writer.header(**{k:v for k,v in item.items() if k!='payload'})
        with open(ROOT/item['path'],'rb') as f:
            if item['op']=='file':
                left=item['size']
                while left:
                    data=f.read(min(BLOCK,left))
                    if not data: raise RuntimeError('Файл изменился во время переноса: '+item['path'])
                    writer.write(data); left-=len(data)
            else:
                for index,length in item['blocks']:
                    f.seek(index*BLOCK)
                    data=f.read(length)
                    if len(data)!=length: raise RuntimeError('Файл изменился во время переноса: '+item['path'])
                    writer.write(data)
    writer.header(op='end')
    out.flush()
    if processes(): raise RuntimeError('Codex снова запущен. Закройте его на обоих Mac и повторите перенос.')
    status('sending',90,current=total,total=total)
    return {'sha256':writer.hash.hexdigest(),'bytes':writer.count,'payload':total,'files':len(work),'deleted':len(deletes)}

class Raw(io.RawIOBase):
    def __init__(self,source):
        self.source=source; self.hash=hashlib.sha256(); self.count=0; self.meter=None
    def readable(self): return True
    def readinto(self,buffer):
        data=self.source.read1(len(buffer)) if hasattr(self.source,'read1') else self.source.read(len(buffer))
        n=len(data); buffer[:n]=data
        self.hash.update(data); self.count+=n
        if self.meter: self.meter(n)
        return n

def clone(root,dest):
    dest.mkdir(mode=0o700)
    for child in sorted(root.iterdir()):
        if not selected(child.name): continue
        target=dest/child.name
        p=subprocess.run(['/bin/cp','-c','-R','-p',str(child),str(target)],capture_output=True)
        if p.returncode:
            if target.is_dir() and not target.is_symlink(): shutil.rmtree(target)
            elif target.exists(): target.unlink()
            if child.is_dir(): shutil.copytree(child,target,symlinks=True)
            else: shutil.copy2(child,target)

def exact(reader,size,sink=None):
    left=size
    while left:
        data=reader.read(min(BLOCK,left))
        if not data: raise RuntimeError('Передача прервана.')
        if sink: sink(data)
        left-=len(data)

def remove(path):
    if path.is_dir() and not path.is_symlink(): shutil.rmtree(path)
    elif path.exists() or path.is_symlink(): path.unlink()

def receive(token,source=None):
    quiet()
    data=incoming(token)
    base=os.path.realpath(data)
    status('comparing',12)
    clone(ROOT,data)
    raw=Raw(source or sys.stdin.buffer)
    reader=io.BufferedReader(raw,BLOCK)
    def record():
        line=reader.readline()
        if not line.endswith(b'\n'): raise RuntimeError('Передача прервана.')
        return json.loads(line)
    def target(rel):
        p=data/checked_path(rel)
        parent=os.path.realpath(p.parent)
        if parent!=base and not parent.startswith(base+os.sep): raise RuntimeError('Недопустимый файл в архиве: '+rel)
        return p
    begin=record()
    if begin.get('op')!='begin': raise RuntimeError('Передача повреждена. История получателя не изменена.')
    total=int(begin['total'])
    if shutil.disk_usage(ROOT.parent).free<total*1.2+512*1024*1024: raise RuntimeError('Недостаточно свободного места на принимающем Mac.')
    raw.meter=Meter('receiving',15,75,max(total,1))
    status('receiving',15,total=total)
    while True:
        item=record()
        op=item.get('op')
        if op=='end': break
        path=target(item.get('path'))
        if op=='delete': remove(path)
        elif op=='dir':
            if path.exists() and not path.is_dir(): remove(path)
            path.mkdir(parents=True,exist_ok=True)
        elif op in ('file','patch'):
            size=int(item['size'])
            if path.is_dir() and not path.is_symlink(): remove(path)
            path.parent.mkdir(parents=True,exist_ok=True)
            if op=='file':
                temp=path.with_name('.transfer-'+path.name)
                with open(temp,'wb') as f: exact(reader,size,f.write)
                os.replace(temp,path)
            else:
                if not path.is_file() or path.is_symlink(): raise RuntimeError('Передача повреждена. История получателя не изменена.')
                os.chmod(path,path.stat().st_mode&0o777|0o600)
                with open(path,'r+b') as f:
                    f.truncate(size)
                    for index,length in item['blocks']:
                        f.seek(int(index)*BLOCK)
                        exact(reader,int(length),f.write)
            os.chmod(path,int(item['mode'])&0o777)
            os.utime(path,(int(item['mtime']),int(item['mtime'])))
        else: raise RuntimeError('Передача повреждена. История получателя не изменена.')
    while reader.read(BLOCK): pass
    result={'sha256':raw.hash.hexdigest(),'bytes':raw.count}
    (checked_token(token)/'received.json').write_text(json.dumps(result))
    status('receiving',90,current=total,total=total)
    return result

def commit(token,expected):
    quiet()
    operation=checked_token(token)
    received=json.loads((operation/'received.json').read_text())
    if received['sha256']!=expected: raise RuntimeError('Контрольная сумма архива не совпадает.')
    data=incoming(token)
    if not any(data.glob('state_*.sqlite')): raise RuntimeError('В архиве отсутствует индекс чатов.')
    status('installing',92)
    database_check(data)
    quiet()
    old=ROOT.parent/('.codex-transfer-old-'+token)
    old.mkdir(mode=0o700)
    journal=operation/'journal.json'
    record={'root':str(ROOT),'incoming':str(data),'old':str(old),'status':'prepared'}
    journal.write_text(json.dumps(record))
    moved=[];added=[]
    try:
        for child in sorted(ROOT.iterdir()):
            if selected(child.name): os.rename(child,old/child.name); moved.append(child.name)
        for child in sorted(data.iterdir()):
            os.rename(child,ROOT/child.name); added.append(child.name)
    except BaseException:
        for name in reversed(added): os.rename(ROOT/name,data/name)
        for name in reversed(moved): os.rename(old/name,ROOT/name)
        old.rmdir()
        journal.unlink()
        raise
    record['status']='committed'
    journal.write_text(json.dumps(record))
    status('installing',97)
    shutil.rmtree(old,ignore_errors=True)
    shutil.rmtree(data,ignore_errors=True)
    status('installing',99)
    return {'ok':True}

def main(args):
    ARGS.clear(); ARGS.update(args)
    action=args['action']; token=args.get('token','')
    if action=='probe': return probe()
    checked_token(token)
    if action=='lock': return acquire(token)
    assert_lock(token)
    threading.Thread(target=heartbeat,daemon=True).start()
    if action in ('blocks','send','receive','commit'):
        try: subprocess.Popen(['/usr/bin/caffeinate','-i','-w',str(os.getpid())],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        except OSError: pass
    if action=='unlock': return release(token,args.get('state','error'),args.get('message',''))
    if action=='stop': return stop()
    if action=='manifest': return manifest()
    if action=='diff': return diff(json.load(sys.stdin))
    if action=='blocks': return blocks(json.load(sys.stdin))
    if action=='send': return send(json.load(sys.stdin))
    if action=='receive': return receive(token)
    if action=='commit': return commit(token,args['sha256'])
    raise RuntimeError('Неизвестная операция.')

MARKER='CODEX_TRANSFER_RESULT '

if __name__=='__main__':
    args=json.loads(sys.argv[1])
    channel=sys.stderr if args.get('action')=='send' else sys.stdout
    try: result=main(args)
    except Exception as e:
        import traceback; traceback.print_exc(file=sys.stderr)
        print(MARKER+json.dumps({'error':str(e)},ensure_ascii=False),file=channel,flush=True); sys.exit(1)
    print(MARKER+json.dumps(result,ensure_ascii=False),file=channel,flush=True)
