# Security policy

## Supported versions

The repository does not yet publish a formal security-support matrix or fix timeline. Verify release support with the maintainers; do not assume that an older release receives security fixes.

## Reporting a vulnerability

Do not publish exploit instructions, credentials, private keys, or sensitive host details in a public issue. Contact the repository maintainers through a private repository security-reporting channel when one is available. Include the affected version, OS, concise impact, and steps to reproduce with disposable data. If no private channel is available, first ask maintainers privately how to submit the details; share only a non-sensitive summary publicly.

This repository does not currently publish a security response-time commitment. Do not assume a report has been received until maintainers acknowledge it.

## Security boundaries

Mutagen remains responsible for sync and forwarding state. MutaUI uses the local Mutagen CLI and OpenSSH client; it does not install a remote agent or bypass strict SSH host-key checks. Treat project hooks and custom commands as executable code. Review the [security notes](docs/security/static-analysis.md) and [remote inspection boundary](docs/security/remote-inspection.md) before using those features.
