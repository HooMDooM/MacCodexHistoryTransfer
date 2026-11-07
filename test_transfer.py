import io,json,os,sqlite3,tempfile,unittest,uuid
from pathlib import Path
from unittest.mock import patch
import agent

class TransferTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.home=Path(self.tmp.name)
        self.source=self.home/'source/.codex'
        self.dest=self.home/'dest/.codex'
        for root in (self.source,self.dest): root.mkdir(parents=True)
        self.patches=[patch.object(agent,'BASE',self.home/'support'),patch.object(agent,'quiet',lambda:None),patch.object(agent,'processes',lambda:[])]
        for p in self.patches:p.start()
        self.addCleanup(self.tmp.cleanup)
        for p in self.patches:self.addCleanup(p.stop)
        self.new_token()
        self.make_db(self.source,'original')
        self.make_db(self.dest,'destination')
        (self.source/'sessions/2026').mkdir(parents=True)
        (self.source/'sessions/2026/chat.jsonl').write_text('original conversation')
        (self.source/'history.jsonl').write_text('h1\n')
        (self.dest/'sessions').mkdir()
        (self.dest/'sessions/chat.jsonl').write_text('destination conversation')
        (self.dest/'auth.json').write_text('destination credential')
        (self.dest/'config.toml').write_text('destination config')

    def new_token(self):
        self.token=uuid.uuid4().hex
        agent.ARGS.update(token=self.token,role='destination',peer='Other')
        agent.acquire(self.token)

    def make_db(self,root,value,rows=1):
        p=root/'state_5.sqlite'
        if p.exists():p.unlink()
        db=sqlite3.connect(p)
        db.execute('CREATE TABLE chats(text TEXT)')
        db.executemany('INSERT INTO chats VALUES (?)',[(value,)]*rows)
        db.commit();db.close()

    def chats(self,root):
        db=sqlite3.connect(root/'state_5.sqlite')
        try: return db.execute('SELECT text FROM chats').fetchone()[0]
        finally: db.close()

    def send(self):
        with patch.object(agent,'ROOT',self.dest): existing=agent.manifest()
        with patch.object(agent,'ROOT',self.source): needed=agent.diff(existing)['paths']
        with patch.object(agent,'ROOT',self.dest): known=agent.blocks(needed)['hashes']
        out=io.BytesIO()
        with patch.object(agent,'ROOT',self.source): sent=agent.send(dict(manifest=existing,hashes=known),out)
        return out.getvalue(),sent

    def receive(self,data):
        with patch.object(agent,'ROOT',self.dest): return agent.receive(self.token,io.BufferedReader(io.BytesIO(data)))

    def transfer(self):
        data,sent=self.send()
        received=self.receive(data)
        self.assertEqual(received['sha256'],sent['sha256'])
        with patch.object(agent,'ROOT',self.dest):
            agent.commit(self.token,sent['sha256'])
            agent.release(self.token,'done','')
        return sent

    def test_full_then_incremental(self):
        sent=self.transfer()
        self.assertEqual((self.dest/'sessions/2026/chat.jsonl').read_text(),'original conversation')
        self.assertFalse((self.dest/'sessions/chat.jsonl').exists())
        self.assertEqual((self.dest/'auth.json').read_text(),'destination credential')
        self.assertEqual((self.dest/'config.toml').read_text(),'destination config')
        self.assertEqual(self.chats(self.dest),'original')
        self.assertEqual(sorted(p.name for p in self.dest.parent.iterdir()),['.codex'])
        self.assertFalse((self.home/'support/lock').exists())
        self.assertEqual(json.loads((self.home/'support/status.json').read_text())['phase'],'done')
        big=self.source/'sessions/2026/big.jsonl'
        big.write_bytes(os.urandom(5*agent.BLOCK))
        self.new_token(); self.transfer()
        with open(big,'ab') as f: f.write(b'new line\n')
        os.utime(big,(1,2_000_000_000))
        (self.source/'sessions/2026/new.jsonl').write_text('new chat')
        self.new_token()
        sent=self.transfer()
        self.assertLess(sent['payload'],2*agent.BLOCK+1_000_000)
        self.assertEqual(big.read_bytes(),(self.dest/'sessions/2026/big.jsonl').read_bytes())
        self.assertEqual((self.dest/'sessions/2026/new.jsonl').read_text(),'new chat')
        self.assertEqual(int((self.dest/'sessions/2026/big.jsonl').stat().st_mtime),2_000_000_000)

    def test_unchanged_sends_only_databases(self):
        self.transfer()
        self.new_token()
        sent=self.transfer()
        self.assertEqual(sent['files'],0)

    def test_database_patch_sends_changed_blocks(self):
        self.make_db(self.source,'x'*1000,rows=3000)
        self.transfer()
        db=sqlite3.connect(self.source/'state_5.sqlite');db.execute("UPDATE chats SET text='changed' WHERE rowid=1");db.commit();db.close()
        size=(self.source/'state_5.sqlite').stat().st_size
        self.new_token()
        sent=self.transfer()
        self.assertLess(sent['payload'],size)
        self.assertEqual((self.source/'state_5.sqlite').read_bytes(),(self.dest/'state_5.sqlite').read_bytes())

    def test_read_only_files_updated(self):
        obj=self.source/'memories/.git/objects/51/abc'
        obj.parent.mkdir(parents=True)
        obj.write_bytes(b'object')
        obj.chmod(0o444)
        self.transfer()
        os.utime(obj,(1,1_900_000_000))
        self.new_token()
        self.transfer()
        copy=self.dest/'memories/.git/objects/51/abc'
        self.assertEqual(copy.read_bytes(),b'object')
        self.assertEqual(copy.stat().st_mode&0o777,0o444)
        self.assertEqual(int(copy.stat().st_mtime),1_900_000_000)

    def test_deleted_files_removed(self):
        self.transfer()
        (self.source/'sessions/2026/chat.jsonl').unlink()
        (self.source/'sessions/2026').rmdir()
        self.new_token()
        sent=self.transfer()
        self.assertFalse((self.dest/'sessions/2026').exists())
        self.assertEqual(sent['deleted'],2)

    def test_bad_hash_keeps_destination(self):
        data,sent=self.send()
        self.receive(data)
        with patch.object(agent,'ROOT',self.dest):
            with self.assertRaisesRegex(RuntimeError,'сумма'):agent.commit(self.token,'bad')
        self.assertEqual(self.chats(self.dest),'destination')

    def test_corrupt_database_keeps_destination(self):
        (self.source/'state_5.sqlite').write_bytes(b'not a database')
        data,sent=self.send()
        self.receive(data)
        with patch.object(agent,'ROOT',self.dest):
            with self.assertRaises(sqlite3.DatabaseError):agent.commit(self.token,sent['sha256'])
        self.assertEqual(self.chats(self.dest),'destination')

    def hostile(self,path,op='file'):
        lines=[dict(op='begin',total=1),dict(op=op,path=path,size=1,mtime=1,mode=0o644)]
        return b''.join(json.dumps(l).encode()+b'\n' for l in lines)+b'x'+json.dumps(dict(op='end')).encode()+b'\n'

    def test_traversal_rejected(self):
        with self.assertRaises(RuntimeError):self.receive(self.hostile('sessions/../../escaped'))
        self.assertFalse((self.home/'dest/escaped').exists())

    def test_absolute_path_rejected(self):
        with self.assertRaises(RuntimeError):self.receive(self.hostile(str(self.home/'escaped')))

    def test_unselected_file_rejected(self):
        with self.assertRaises(RuntimeError):self.receive(self.hostile('auth.json'))
        self.assertEqual((self.dest/'auth.json').read_text(),'destination credential')

    def test_symlink_in_source_rejected(self):
        (self.source/'sessions/link').symlink_to('/tmp')
        with self.assertRaises(RuntimeError):self.send()

    def test_truncated_stream_rejected(self):
        data,sent=self.send()
        with self.assertRaises(RuntimeError):self.receive(data[:-30])

    def test_failed_rename_rolls_back(self):
        data,sent=self.send()
        self.receive(data)
        original=os.rename
        def fail(source,dest,*args,**kwargs):
            if Path(dest)==self.dest/'state_5.sqlite' and '.codex-transfer-incoming-' in str(source):raise OSError('simulated disk failure')
            return original(source,dest,*args,**kwargs)
        with patch.object(agent,'ROOT',self.dest),patch.object(agent.os,'rename',fail):
            with self.assertRaises(OSError):agent.commit(self.token,sent['sha256'])
        self.assertEqual(self.chats(self.dest),'destination')
        self.assertEqual((self.dest/'sessions/chat.jsonl').read_text(),'destination conversation')

    def test_failed_release_cleans_incoming(self):
        data,sent=self.send()
        self.receive(data)
        with patch.object(agent,'ROOT',self.dest): agent.release(self.token,'error','Сбой')
        self.assertEqual(sorted(p.name for p in self.dest.parent.iterdir()),['.codex'])
        self.assertEqual(json.loads((self.home/'support/status.json').read_text())['phase'],'error')

    def test_lock_rejects_second_operation(self):
        with self.assertRaises(RuntimeError):agent.acquire(uuid.uuid4().hex)
        with self.assertRaises(RuntimeError):agent.assert_lock(uuid.uuid4().hex)

    def test_wal_rows_transferred(self):
        db=sqlite3.connect(self.source/'state_5.sqlite')
        db.execute('PRAGMA journal_mode=WAL')
        db.execute("INSERT INTO chats VALUES ('wal row')")
        db.commit()
        data,sent=self.send()
        db.close()
        self.receive(data)
        with patch.object(agent,'ROOT',self.dest): agent.commit(self.token,sent['sha256'])
        read=sqlite3.connect(self.dest/'state_5.sqlite')
        self.assertEqual(read.execute('SELECT count(*) FROM chats').fetchone()[0],2)
        read.close()

if __name__=='__main__':unittest.main(verbosity=2)
