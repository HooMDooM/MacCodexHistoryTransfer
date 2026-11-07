# Contributing

Build and test on macOS 13 or later with Apple Command Line Tools and Python 3.

```sh
python3 -m unittest -v test_transfer test_pairing
swiftc Discovery.swift Localization.swift Tests/DiscoveryTests.swift -o /tmp/discovery-tests
/tmp/discovery-tests
python3 build.py
```

For optional local-network verification:

```sh
swiftc Discovery.swift Localization.swift Tests/BonjourIntegration.swift -o /tmp/bonjour-tests
/tmp/bonjour-tests
```

The Bonjour test publishes and discovers a temporary service on your Mac. It may require Local Network permission. It is intentionally excluded from hosted CI.

Keep changes focused, preserve both interface languages and add regression coverage for changes to pairing or transfer behavior. Use temporary fixtures for tests; never run automated transfer tests against your real `~/.codex` directory.

For UI changes, include screenshots with fictional computer and account names. For transfer changes, describe behavior under interruption and low disk space. Document any storage schema assumptions.

Do not attach private keys, passwords, chat transcripts, database files or unredacted logs to issues or pull requests.
