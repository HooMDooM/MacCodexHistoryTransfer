Mac Codex History Transfer 0.4.0

1. Install and open the app on both Macs on the same network. Allow Local Network access.
2. If the app asks to turn on Remote Login, click “Turn On” and allow access for your user. This is needed once.
3. Click “Find Mac”, choose the other Mac and click “Connect”.
4. On the first connection, compare the code shown with the code at the bottom of the app window on the other Mac, then enter the other Mac’s user password. The password is not saved.
5. Choose the direction and click “Transfer”. Codex closes on both Macs, and the percentage is shown on both.
6. When it finishes, open Codex on the receiving Mac.

Only chats and history are transferred: sessions, archived_sessions, history.jsonl, session_index.jsonl, memories and the state/thread_history/goals/memories databases. Sign-in, settings, plugins and projects stay on each Mac.

No backup is made: the history on the receiving Mac is replaced entirely. Data is streamed without an intermediate archive and verified by checksum and SQLite checks before replacement. If anything fails, the receiving history is not changed.

Requirements: macOS 13+, the same Codex version and the same home path on both Macs, Python 3 (Command Line Tools). Free space on the receiving Mac at least the size of the history.

Connection key: ~/Library/Application Support/Codex Transfer/keys/id_ed25519. It is added to the other Mac’s ~/.ssh/authorized_keys marked CodexTransfer; remove that line to revoke access.

After a crash: make sure no agent/transfer.py processes run on either Mac, then delete ~/Library/Application Support/Codex Transfer/lock. If a journal.json in operations has status prepared, the original history files are in ~/.codex-transfer-old-<operation>.

The app is signed ad-hoc without notarization. On the other Mac you may need “Open Anyway” in Privacy & Security settings.
