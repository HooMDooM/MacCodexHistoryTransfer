# Changelog

## 0.4.0

First public release.

- Native SwiftUI interface with discovery, connection and transfer screens.
- Nearby Mac discovery through Bonjour.
- Guided SSH pairing with host-key verification and a one-time password prompt.
- English and Russian, selected automatically from macOS language preferences.
- Progress reporting on both Macs.
- Incremental, block-aware history transfer over SSH.
- Checksum and SQLite validation before installation.
- Staged history replacement with rollback for handled installation errors.
- Universal macOS application for Apple silicon and Intel.

Destination history is replaced, not merged. Version 0.4.0 does not retain a backup after a successful transfer.
