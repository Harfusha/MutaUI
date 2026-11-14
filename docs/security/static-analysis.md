# Static security checks

`pyproject.toml` extends the existing Ruff gate with selected Bandit-compatible rules for suspicious credentials, unsafe deserialization/evaluation, weak hashes, unsafe subprocess options, and SQL construction. CI already runs `ruff check .`, so these checks run on push, pull request, and Windows release builds.

The CI and tagged-release workflows also audit the declared runtime, build, and quality dependency sets with `pip-audit`, lint workflow YAML with `yamllint`, and validate GitHub Actions expressions and workflow structure with `actionlint`. The actionlint Linux archive is version-pinned and checked against the upstream SHA-256 before execution. `detect-secrets-hook` scans tracked files against `.secrets.baseline` to catch new findings. Four reviewed baseline entries across `tests/test_insights.py`, `tests/test_mainwindow_flows.py`, and `tests/test_portable_bundle.py` are synthetic test fixtures labeled as false positives; they must not be used as credentials.

Local equivalents are `uv run python -m pip_audit -r requirements.txt -r requirements-build.txt -r requirements-quality.txt`, `uv run python -m yamllint -s .github/workflows .yamllint`, `actionlint .github/workflows/*.yml`, and `git ls-files -z | xargs -0 detect-secrets-hook --baseline .secrets.baseline` on a POSIX shell. These tools provide automated checks, not proof that the repository contains no secrets or that every dependency license is compatible with a distribution choice.

CI also runs `mypy --strict src/mutaui`. `follow_imports = "skip"` keeps the new typed-core boundary explicit while the legacy client and its third-party psutil typing debt remain unmigrated.

Ruff format checking is required for the extracted `src/mutaui` package and its focused contract tests. The existing legacy tree still has unrelated formatting debt and is not mass-rewritten.

Markdown documentation is scanned with PyMarkdown. MD013 is disabled because existing prose, tables, and command examples intentionally exceed 80 columns; MD029 is disabled to accept the repository's numbered-list style. All other default rules run over `docs/` recursively.

## Reviewed exceptions

- `mutagen_client.py` ignores Ruff S603. The reviewed `subprocess.run` call receives an argument list and explicitly sets `shell=False`. The executable is resolved and checked; area/action pairs are allowlisted; regular session actions require an explicit identifier; bulk actions validate, deduplicate and cap target IDs. Create options represent intentional Mutagen CLI arguments. Regression tests assert exact argument lists and `shell is False`. Re-review this exception if command construction changes.
- `scripts/run_self_test.py` ignores Ruff S603. It launches the explicitly supplied packaged executable as one argv element with only the fixed `--self-test` flag and `shell=False`; it never builds or evaluates a command string.
- `scripts/check_dependency_exports.py` ignores Ruff S603. It invokes the fixed `uv export` executable with repository-owned requirement filenames and the fixed dependency-group list, writes only to a temporary directory, and compares the generated pins with checked-in exports.
- `ssh_profiles.py` ignores Ruff S603 for local OpenSSH inspection and an explicit user-requested connection test. Calls use fixed argument lists, `shell=False`, strict timeouts, and validated aliases; connection tests force `BatchMode=yes` and `StrictHostKeyChecking=yes`. No private-key or known-hosts data is written.
- `monitoring.py` and `async_recorder.py` ignore S608. Dynamic SQL fragments contain column names only from the fixed module-level `METRIC_COLUMNS` and `REMOTE_COLUMNS` tuples. Every data value remains a bound SQLite parameter. Re-review if a column list ever derives from settings, files, or user input.

The CI gate does not suppress assertions in application code or tests. Global Ruff formatting remains separate: the existing legacy tree has 36 files that would be rewritten, so formatting must proceed incrementally without bulk churn.
