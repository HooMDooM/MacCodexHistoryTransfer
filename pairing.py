import base64,json,os,pty,re,select,signal,subprocess,sys,termios,time
from pathlib import Path
import transfer
from transfer import connection_error,log,ssh_command

KEY=Path.home()/'Library/Application Support/Codex Transfer/keys/id_ed25519'

def ask(kind,message):
    print(json.dumps({'prompt':kind,'message':message},ensure_ascii=False),flush=True)
    line=sys.stdin.readline()
    if not line: raise RuntimeError('Подключение отменено.')
    answer=json.loads(line).get('answer')
    if answer is None: raise RuntimeError('Подключение отменено.')
    return str(answer)

def ensure_key():
    KEY.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    if not KEY.exists():
        p=subprocess.run(['/usr/bin/ssh-keygen','-q','-t','ed25519','-N','','-C','CodexTransfer','-f',str(KEY)],capture_output=True)
        if p.returncode: raise RuntimeError('Не удалось создать ключ подключения.')
    if KEY.is_symlink(): raise RuntimeError('Некорректный файл ключа подключения.')
    KEY.chmod(0o600)
    result=subprocess.run(['/usr/bin/ssh-keygen','-y','-P','','-f',str(KEY)],capture_output=True,text=True)
    if result.returncode: raise RuntimeError('Не удалось прочитать ключ подключения.')
    fields=result.stdout.strip().split()
    public=" ".join(fields[:2])
    if not re.fullmatch(r'ssh-ed25519 [A-Za-z0-9+/=]+',public): raise RuntimeError('Некорректный ключ подключения.')
    return public

def install_command(public):
    code="""import os,pathlib
p=pathlib.Path.home()/'.ssh'
if p.is_symlink(): raise RuntimeError('Symlink .ssh is unsupported')
p.mkdir(mode=0o700,exist_ok=True)
f=p/'authorized_keys'
if f.is_symlink(): raise RuntimeError('Symlink authorized_keys is unsupported')
key=PUBLIC
existing=f.read_text() if f.exists() else ''
if not any(key.split()[1] in line.split() for line in existing.splitlines()):
 with f.open('a') as out:
  out.write(('\\n' if existing and not existing.endswith('\\n') else '')+'restrict '+key+' CodexTransfer\\n')
p.chmod(0o700)
f.chmod(0o600)
print('CODEX_TRANSFER_PAIRED')
""".replace('PUBLIC',repr(public))
    encoded=base64.b64encode(code.encode()).decode()
    import shlex
    return 'python3 -c '+shlex.quote("import base64;exec(base64.b64decode('"+encoded+"'))")

def finalize(host):
    local=transfer.call(None,'probe')
    remote=transfer.call(host,'probe')
    transfer.compatible(local,remote)
    transfer.event(event='connected',name=remote['name'],host=host,version=remote['app']['version'])
    log('Второй Mac готов. Теперь можно переносить историю.')

def pair(host):
    if not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.@-]*',host): raise RuntimeError('Выберите второй Mac из списка.')
    public=ensure_key()
    log('Проверяю подключение…')
    try:
        transfer.call(host,'probe')
        return finalize(host)
    except RuntimeError as e:
        if 'не настроен' not in str(e) and 'не подключён' not in str(e): raise
    log('Подключаю второй Mac…')
    command=ssh_command(host,batch=False)+[install_command(public)]
    pid,fd=pty.fork()
    if pid==0:
        os.environ['LC_ALL']='C'
        os.execv('/usr/bin/ssh',command)
    pending='';transcript='';done=False;status=None;deadline=time.monotonic()+90;password_used=False
    try:
        while time.monotonic()<deadline:
            ready,_,_=select.select([fd],[],[],.2)
            if ready:
                try: data=os.read(fd,8192)
                except OSError: data=b''
                if not data:
                    _,status=os.waitpid(pid,0);done=True;break
                text=data.decode(errors='replace');pending+=text;transcript=(transcript+text)[-32768:]
                if 'Are you sure you want to continue connecting' in pending:
                    match=re.search(r'SHA256:[A-Za-z0-9+/]+',pending)
                    if not match: raise RuntimeError('Не удалось проверить код второго Mac.')
                    answer=ask('trust',host+'\n'+match.group(0))
                    if answer!='yes': raise RuntimeError('Подключение отменено.')
                    os.write(fd,b'yes\n');pending='';deadline=time.monotonic()+90
                elif re.search(r'(?i)(?:password|passphrase)[^\r\n]*:\s*$',pending):
                    if password_used: raise RuntimeError('Пароль не подошёл. Попробуйте подключиться ещё раз.')
                    if 'passphrase' in pending.lower(): raise RuntimeError('Ключ требует пароль. Используйте отдельный ключ Codex Transfer.')
                    password=ask('password',host)
                    if '\n' in password or '\r' in password: raise RuntimeError('Некорректный пароль.')
                    attrs=termios.tcgetattr(fd);attrs[3]&=~termios.ECHO;termios.tcsetattr(fd,termios.TCSANOW,attrs)
                    os.write(fd,password.encode()+b'\n');password='';password_used=True;pending='';deadline=time.monotonic()+90
            ended,child_status=os.waitpid(pid,os.WNOHANG)
            if ended:
                done=True;status=child_status
                while select.select([fd],[],[],0)[0]:
                    try: tail=os.read(fd,8192)
                    except OSError: break
                    if not tail: break
                    transcript=(transcript+tail.decode(errors='replace'))[-32768:]
                break
        if not done:
            ended,child_status=os.waitpid(pid,os.WNOHANG)
            if ended: done=True;status=child_status
        if not done: raise RuntimeError('Время подключения истекло. Повторите попытку.')
        if status!=0 or 'CODEX_TRANSFER_PAIRED' not in transcript:
            if password_used: raise RuntimeError('Не удалось настроить доступ. Проверьте пароль пользователя и наличие Python 3 на втором Mac.')
            if 'python3' in transcript and ('not found' in transcript or 'developer tools' in transcript): raise RuntimeError('На втором Mac требуется Python 3. Установите там Command Line Tools: xcode-select --install')
            raise RuntimeError(connection_error(host,transcript.encode()))
        log('Подключение настроено. Пароль не сохранён.')
        finalize(host)
    finally:
        os.close(fd)
        if not done:
            try: os.kill(pid,signal.SIGTERM)
            except ProcessLookupError: pass
            os.waitpid(pid,0)

if __name__=='__main__':
    try: pair(sys.argv[1])
    except Exception as e: log('ОШИБКА: '+str(e));sys.exit(1)
