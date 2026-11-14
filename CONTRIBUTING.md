# Contributing

Thanks for helping improve Mutagen Control. Keep changes focused, preserve Mutagen as the source of truth, and never claim platform or runtime acceptance from source inspection alone.

## Development setup

- Use Python 3.12, the repository's configured target. Install uv with `python -m pip install uv==0.13.8`, then run `uv sync --locked --group build --group test --group quality`. The committed `uv.lock` is authoritative; the `requirements*.txt` files are pinned compatibility exports.
- After changing dependencies in `pyproject.toml`, run `uv lock`, then regenerate the pip exports with `uv export --locked --no-default-groups --no-emit-project --no-hashes --output-file requirements.txt`, `uv export --locked --no-default-groups --only-group build --only-group test --only-group quality --no-emit-project --no-hashes --output-file requirements-build.txt`, and `uv export --locked --no-default-groups --only-group test --only-group quality --no-emit-project --no-hashes --output-file requirements-quality.txt`.
- On Windows, `start.cmd` creates the local environment; see the [README](README.md) for the build scripts.
- On Linux, install the Qt runtime libraries listed in `.github/workflows/ci.yml` before running the GUI. On macOS, use a native macOS environment for GUI and packaging work.
- Install Mutagen CLI separately only when performing an explicitly isolated integration test. Never point integration tests at a normal user or production daemon.

## Checks

Run `uv run python verify_source.py`, `uv run python -m ruff check .`, and the portable tests with `uv run python -m pytest -q tests --ignore=tests/test_gui_smoke.py`. On Windows PowerShell, run `$env:QT_QPA_PLATFORM="offscreen"; uv run python -m pytest -q tests/test_gui_smoke.py` before packaging. The Windows workflow runs packaged self-tests for both onedir and onefile executables. For isolated real-Mutagen and SSH procedures, follow [runtime and integration testing](docs/TESTING.md); those checks require explicit test fixtures and do not prove all operating systems.

Run `uv run python -m mkdocs build --strict` after documentation changes. Keep English and Czech user-facing copy aligned. Update both checked-in settings-reference pages through the UI help registry generator, then verify them:

```powershell
python scripts/generate_settings_reference.py
python scripts/generate_settings_reference.py --output docs/reference/configuration-fields.md
python scripts/generate_settings_reference.py --check
python scripts/generate_settings_reference.py --check --output docs/reference/configuration-fields.md
```

For visible UI changes, regenerate captures with the documented demo workflow and manually inspect the actual images for clipping, keyboard focus, and readability. Do not substitute mockups for application screenshots.

## Pull requests

Use the pull request template. Link the relevant requirement and acceptance IDs, describe behavior and migration impact, include verification commands and their real results, and state remaining platform or live-service gaps. Do not stage or include generated binaries, local secrets, credentials, real user data, or unrelated workspace changes.
