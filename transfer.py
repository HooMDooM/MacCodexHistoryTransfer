import base64,json,os,re,shlex,subprocess,sys,threading,uuid
from pathlib import Path

from localization import translate

AGENT=Path(__file__).with_name('agent.py')
MARKER='CODEX_TRANSFER_RESULT '
HOST=re.compile(r'[A-Za-z0-9_][A-Za-z0-9_.@-]*')

def log(message): print(translate(message),flush=True)

def event(**values): print(json.dumps(values,ensure_ascii=False),flush=True)

def connection_error(host,stderr):
    error=stderr.decode(errors='replace').strip()
    lower=error.lower()
    if 'connection refused' in lower:
        return 'Mac найден, но удалённый вход на нём выключен. Откройте приложение на втором Mac и включите доступ.'
    if 'remote host identification has changed' in lower:
        return 'Ключ SSH второго Mac изменился. Проверьте его подлинность перед обновлением known_hosts.\n'+error
    if 'host key verification failed' in lower or 'strict checking' in lower:
        return 'Этот Mac ещё не подключён. Нажмите «Подключить».'
    if 'permission denied' in lower:
        return 'Доступ ещё не настроен. Нажмите «Подключить» и введите пароль пользователя второго Mac.'
    if 'operation timed out' in lower or 'connection timed out' in lower or 'no route to host' in lower:
        return 'Второй Mac не отвечает. Проверьте, что он включён и подключён к той же сети.\n'+error
    return error or 'Нет ответа от '+(host or 'этого Mac')

def ssh_command(host,batch=True):
    key=Path.home()/'Library/Application Support/Codex Transfer/keys/id_ed25519'
    command=['/usr/bin/ssh','-T','-o','ConnectTimeout=10','-o','ServerAliveInterval=15','-o','ServerAliveCountMax=4','-o','StrictHostKeyChecking='+('yes' if batch else 'ask'),'-o','BatchMode='+('yes' if batch else 'no')]
    if key.exists(): command+=['-i',str(key),'-o','IdentitiesOnly=yes','-o','IdentityAgent=none']
    if not batch: command+=['-o','HostKeyAlgorithms=ssh-ed25519','-o','NumberOfPasswordPrompts=1','-o','PreferredAuthentications=publickey,password,keyboard-interactive']
    return command+[host]

def agent_command(host,args):
    text=json.dumps(args,ensure_ascii=False)
    if not host: return [sys.executable,str(AGENT),text]
    encoded=base64.b64encode(AGENT.read_bytes()).decode()
    payload=base64.b64encode(text.encode()).decode()
    code="import base64,sys;sys.argv=['agent',base64.b64decode('"+payload+"').decode()];exec(compile(base64.b64decode('"+encoded+"'),'agent','exec'))"
    return ssh_command(host)+['python3 -c '+shlex.quote(code)]

def parse(host,output,stderr):
    for line in reversed(output.decode(errors='replace').splitlines()):
        if line.startswith(MARKER):
            result=json.loads(line[len(MARKER):])
            if 'error' in result: raise RuntimeError(result['error'])
            return result
    raise RuntimeError(connection_error(host,stderr))

def call(host,action,token='',data=None,**values):
    command=agent_command(host,dict(action=action,token=token,**values))
    if data is None: p=subprocess.run(command,stdin=subprocess.DEVNULL,capture_output=True,timeout=7200)
    else: p=subprocess.run(command,input=json.dumps(data).encode(),capture_output=True,timeout=7200)
    return parse(host,p.stdout,p.stderr)

def compatible(local,remote):
    if local['host']==remote['host']: raise RuntimeError('Выбран тот же компьютер.')
    if local['home']!=remote['home']: raise RuntimeError('Домашние папки должны совпадать на обоих Mac: '+local['home']+' ≠ '+remote['home'])
    if local['app']['version']!=remote['app']['version']: raise RuntimeError('Установите одинаковую версию Codex на обоих Mac.')

def stream(source,dest,token,payload,context):
    sender=subprocess.Popen(agent_command(source,dict(action='send',token=token,**context[source])),stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    receiver=subprocess.Popen(agent_command(dest,dict(action='receive',token=token,**context[dest])),stdin=sender.stdout,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    sender.stdout.close()
    def feed():
        try:
            sender.stdin.write(json.dumps(payload).encode()); sender.stdin.close()
        except OSError: pass
    collected={}
    writer=threading.Thread(target=feed,daemon=True)
    reader=threading.Thread(target=lambda:collected.update(err=sender.stderr.read()),daemon=True)
    writer.start(); reader.start()
    out,err=receiver.communicate()
    sender.wait(); reader.join(); writer.join()
    sent_error=None
    try: sent=parse(source,collected.get('err',b''),collected.get('err',b''))
    except RuntimeError as e: sent_error=e
    try: received=parse(dest,out,err)
    except RuntimeError as e:
        detail=err.decode(errors='replace').strip()[-2000:]
        if detail and detail not in str(e): raise RuntimeError(str(e)+'\n'+detail)
        raise
    if sent_error: raise sent_error
    if received['sha256']!=sent['sha256'] or received['bytes']!=sent['bytes']: raise RuntimeError('Передача повреждена. История получателя не изменена.')
    return sent

def main():
    if len(sys.argv)!=4: raise RuntimeError('Ожидаются режим, SSH-адрес и направление.')
    mode,host,direction=sys.argv[1:]
    if mode!='transfer' or direction not in ('push','pull'): raise RuntimeError('Неизвестный режим.')
    if not HOST.fullmatch(host): raise RuntimeError('Выберите второй Mac из списка.')
    token=uuid.uuid4().hex
    log('Проверяю подключение…')
    local=call(None,'probe'); remote=call(host,'probe')
    log('Этот Mac: '+local['name']+' · Codex '+local['app']['version'])
    log('Другой Mac: '+remote['name']+' · Codex '+remote['app']['version'])
    compatible(local,remote)
    source,dest=(None,host) if direction=='push' else (host,None)
    context={None:dict(role='source' if direction=='push' else 'destination',peer=remote['name']),host:dict(role='destination' if direction=='push' else 'source',peer=local['name'])}
    locked=[];state='error';message=''
    try:
        for target in [None,host]:
            call(target,'lock',token,**context[target]); locked.append(target)
        for target in [None,host]:
            log('Закрываю Codex: '+(remote['name'] if target else local['name']))
            call(target,'stop',token,**context[target])
        log('Сравниваю историю на обоих Mac…')
        existing=call(dest,'manifest',token,**context[dest])
        needed=call(source,'diff',token,data=existing,**context[source])['paths']
        known=call(dest,'blocks',token,data=needed,**context[dest])['hashes'] if needed else {}
        sent=stream(source,dest,token,dict(manifest=existing,hashes=known),context)
        log('Передано изменений: '+str(round(sent['payload']/1073741824,2))+' ГБ, файлов: '+str(sent['files'])+', удалено: '+str(sent['deleted']))
        log('Проверяю базы и устанавливаю историю…')
        call(dest,'commit',token,sha256=sent['sha256'],**context[dest])
        state='done'
        log('Готово. Откройте Codex на принимающем Mac.')
    except Exception as e:
        message=str(e)
        raise
    finally:
        for target in reversed(locked):
            try: call(target,'unlock',token,state=state,message=message,**context[target])
            except Exception as e: log('Не удалось снять блокировку: '+str(e))

if __name__=='__main__':
    try: main()
    except Exception as e: log('ОШИБКА: '+str(e)); sys.exit(1)
