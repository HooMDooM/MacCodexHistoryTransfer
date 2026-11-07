import ast,base64,contextlib,io,os,shlex,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import pairing,transfer,localization

class PairingTests(unittest.TestCase):
    def test_real_keygen_comment_and_existing_key_reuse(self):
        with tempfile.TemporaryDirectory() as tmp:
            key=Path(tmp)/'keys/id_ed25519'
            with patch.object(pairing,'KEY',key):
                public=pairing.ensure_key()
                original=key.read_bytes()
                self.assertEqual(len(public.split()),2)
                self.assertEqual(public.split()[0],'ssh-ed25519')
                self.assertEqual(pairing.ensure_key(),public)
                self.assertEqual(key.read_bytes(),original)
                self.assertEqual(key.stat().st_mode&0o777,0o600)
                self.assertIn('CodexTransfer',key.with_suffix('.pub').read_text())

    def test_key_install_preserves_existing_keys_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/'.ssh').mkdir()
            f=root/'.ssh/authorized_keys'
            f.write_text('ssh-ed25519 EXISTING OtherDevice')
            cmd=pairing.install_command('ssh-ed25519 AAAATEST')
            outer=shlex.split(cmd)[2]
            encoded=outer.split("base64.b64decode('")[1].split("')")[0]
            code=base64.b64decode(encoded).decode()
            with patch('pathlib.Path.home',return_value=root),contextlib.redirect_stdout(io.StringIO()):
                exec(code,{})
                exec(code,{})
            self.assertEqual(f.read_text().count('AAAATEST'),1)
            self.assertIn('EXISTING OtherDevice\n',f.read_text())
            self.assertIn('restrict ssh-ed25519 AAAATEST CodexTransfer',f.read_text())
            self.assertEqual(f.stat().st_mode&0o777,0o600)

    def test_password_and_host_confirmation_through_pty(self):
        self.run_fake(True)

    def test_cancel_stops_setup(self):
        self.run_fake(False)

    def run_fake(self,accept):
        with tempfile.TemporaryDirectory() as tmp:
            fake=Path(tmp)/'fake.py'
            fake.write_text("import sys,time,termios\na=termios.tcgetattr(0);a[3]&=~termios.ECHO;termios.tcsetattr(0,termios.TCSANOW,a)\nprint('ED25519 key fingerprint is SHA256:abcd1234.',flush=True)\nprint('Are you sure you want to continue connecting (yes/no/[fingerprint])?',end='',flush=True)\nassert input()=='yes'\nprint(\"user@mac.local password: \",end='',flush=True)\nassert input()=='test-secret-value'\nprint('CODEX_TRANSFER_PAIRED',flush=True)\n")
            original=os.execv
            def fake_exec(exe,args): original(sys.executable,[sys.executable,str(fake)])
            answers=['yes','test-secret-value'] if accept else ['no']
            output=io.StringIO()
            with patch.object(pairing,'ensure_key',return_value='ssh-ed25519 AAAATEST'),patch.object(pairing,'ssh_command',return_value=['ssh']),patch.object(pairing.os,'execv',side_effect=fake_exec),patch.object(pairing,'ask',side_effect=answers),patch.object(transfer,'call',side_effect=RuntimeError('Доступ ещё не настроен.')),patch.object(pairing,'finalize') as ready,contextlib.redirect_stdout(output):
                if accept:
                    pairing.pair('user@mac.local')
                    ready.assert_called_once_with('user@mac.local')
                else:
                    with self.assertRaisesRegex(RuntimeError,'отменено'):pairing.pair('user@mac.local')
            self.assertNotIn('test-secret-value',output.getvalue())

    def test_already_paired_skips_password(self):
        local={'host':'a','home':'/Users/u','name':'A','app':{'version':'1'}}
        remote={'host':'b','home':'/Users/u','name':'B','app':{'version':'1'}}
        output=io.StringIO()
        with patch.object(pairing,'ensure_key',return_value='ssh-ed25519 AAAATEST'),patch.object(transfer,'call',side_effect=[remote,local,remote]),patch.object(pairing.pty,'fork') as fork,contextlib.redirect_stdout(output):
            pairing.pair('user@mac.local')
        fork.assert_not_called()
        self.assertIn('"event": "connected"',output.getvalue())

    def test_version_mismatch_reported(self):
        local={'host':'a','home':'/Users/u','name':'A','app':{'version':'1'}}
        remote={'host':'b','home':'/Users/u','name':'B','app':{'version':'2'}}
        with patch.object(transfer,'call',side_effect=[local,remote]):
            with self.assertRaisesRegex(RuntimeError,'версию'):pairing.finalize('user@mac.local')

    def test_english_covers_all_python_messages(self):
        with patch.object(localization,'LANGUAGE','en'):
            for name in ['agent.py','transfer.py','pairing.py']:
                for node in ast.walk(ast.parse(Path(name).read_text())):
                    if isinstance(node,ast.Constant) and isinstance(node.value,str):
                        import re
                        if re.search('[А-Яа-я]',node.value):
                            self.assertIsNone(re.search('[А-Яа-я]',localization.translate(node.value)),name+': '+node.value)

if __name__=='__main__':unittest.main(verbosity=2)
