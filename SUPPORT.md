# Support

## Before reporting a problem

1. Record the MutaUI release, operating system and architecture, and output of `mutagen version`.
2. Check the [installation guide](docs/installation.md), [troubleshooting guide](docs/troubleshooting.md), and [capability matrix](docs/capability-matrix.md). Linux support evidence currently covers the Ubuntu CI image; other distributions remain unverified.
3. Reproduce with disposable folders when the issue involves sync, forwarding, replacement, projects, or recovery. Do not experiment on the only copy of important data.
4. Collect only relevant diagnostic output. Remove tokens, private paths, hostnames, account names, keys, and personal data. Never attach private key contents or production data.

## Bug reports and questions

Use the repository's Issues tab for reproducible defects and feature requests. Include expected and observed behavior, exact steps, versions, and whether the issue occurs in demo or live mode. For suspected vulnerabilities, follow [SECURITY.md](SECURITY.md) instead of posting exploit details publicly.

## Current verification limits

Automated tests, packaged self-tests, hosted CI, and manual OS acceptance are different kinds of evidence. Check [acceptance traceability](docs/acceptance-traceability.md) for the current results and open gates. A successful local run does not establish compatibility with every Mutagen version, endpoint type, OS release, or Linux distribution.
