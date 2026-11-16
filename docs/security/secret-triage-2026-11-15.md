# Secret scanner triage — 2026-11-15

Hosted CI [run 43710608113](https://github.com/Harfusha/MutaUI/actions/runs/43710608113) reported **14** high-entropy hex matches. Review confirmed 13 as public non-credential identifiers: three Git commit IDs in the two `.local-ai-hub/plans` JSON files, six public binary/commit/fingerprint values in the two checked-in benchmark result JSON files, and four public SHA-256 digests in packaging/CI scripts and tests. The remaining finding pointed to `packaging/linux/build-packages.sh:52`, which loads the manifest and contains no digest; the actual appimagetool digest is in `supply-chain.json`. Both POSIX and Windows baseline path records for that stale finding were removed.

| Source | Matches | Explanation |
| --- | ---: | --- |
| `.local-ai-hub/plans/plan_af94bba41219.plan.json` | 1 | Public Git revision ID |
| `.local-ai-hub/plans/plan_c16d3c0122a2.plan.json` | 2 | Public Git revision IDs |
| `benchmarks/results/windows-onefile-startup-2026-11-14.json` | 3 | Binary digest, revision, non-authentication benchmark fingerprint |
| `benchmarks/results/windows-packaged-startup-2026-11-14.json` | 3 | Binary digest, revision, non-authentication benchmark fingerprint |
| `packaging/linux/supply-chain.json` | 1 | Public appimagetool checksum |
| `scripts/ci/install_actionlint.py` and `tests/test_ci_runner.py` | 2 | Public actionlint checksum |
| `tests/test_packaging_linux.py` | 1 | Public appimagetool checksum |

The baseline is restricted to the **exact source paths and hashed values**. It does not suppress the HexHighEntropyString plugin, other paths, or future changed tokens. Remaining reviewed findings have `is_secret=false` with a documented explanation here. Public benchmark result paths should also be sanitized; see follow-up privacy task.

The CI must still reject a freshly injected random high-entropy token; do not treat a clean baseline as sufficient proof.
