# Reviewing secret-scanner false positives

The repository runs `detect-secrets-hook --baseline .secrets.baseline`
against every tracked file in GitHub Actions. The baseline must **never**
be a mechanism to silently approve newly discovered credentials.

The entries added on 2026-11-15 are reviewed false positives consisting
of Git commit object identifiers, reproducible build SHA-256 digests,
benchmark source-tree fingerprints, and pinned third-party archive hashes.
They are listed with both POSIX and Windows path separators to make the
baseline portable across all supported CI runners. No security detector or
repository path was excluded to suppress these findings.

To review a future scanner failure:

1. Examine the exact file and line reported by the workflow; treat unknown
   tokens as potential credentials until verified.
2. Remove and rotate genuine secrets. Do not store their values in this file.
3. For *verified non-secret checksums*, document the provenance and add only
   their individual SHA-1 detector fingerprints to the baseline. Use
   `detect-secrets audit .secrets.baseline` for human review.
4. Re-run the full tracked-file scan in all four CI environments. A clean
   baseline does not substitute for a review of new repository content.

The existing test-fixture credentials are deliberately fictional and are
individually marked as non-secrets in the baseline. A record marked
`is_secret: false` must only be retained after human inspection.
