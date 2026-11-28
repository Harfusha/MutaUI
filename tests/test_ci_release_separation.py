"""PR CI must not contain code-signing credentials or unreachable release steps."""

from pathlib import Path


def test_pull_request_workflow_does_not_request_release_secrets() -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "contents: read" in workflow
    assert "cancel-in-progress: true" in workflow
    assert "github.event.pull_request.number || github.ref" in workflow
    assert "id-token: write" not in workflow
    assert "attestations: write" not in workflow
    assert "APPLE_CERTIFICATE_BASE64" not in workflow
    assert "APPLE_NOTARY_KEY_BASE64" not in workflow
    assert "WINDOWS_SIGNING_CERT" not in workflow
    assert "notarytool" not in workflow
    assert "refs/tags/" not in workflow


def test_ci_and_release_workflows_do_not_schedule_macos_runners() -> None:
    for workflow_path in (".github/workflows/ci.yml", ".github/workflows/release.yml"):
        workflow = Path(workflow_path).read_text(encoding="utf-8")
        assert "os: [windows-latest, ubuntu-latest]" in workflow
        assert "macos-latest" not in workflow
        assert "macos-15-intel" not in workflow


def test_release_workflow_publishes_without_signing_or_provenance() -> None:
    release = Path(".github/workflows/release.yml").read_text(encoding="utf-8")
    assert "APPLE_CERTIFICATE_BASE64" not in release
    assert "APPLE_NOTARY_KEY_BASE64" not in release
    assert "WINDOWS_SIGNING_CERT_BASE64" not in release
    assert "notarytool" not in release
    assert "codesign" not in release
    assert "signtool" not in release
    assert "Get-AuthenticodeSignature" not in release
    assert "id-token: write" not in release
    assert "attestations: write" not in release
    assert "attestations: read" not in release
    assert "actions/attest" not in release
    assert "gh attestation verify" not in release
    assert "Upload release package" in release


def test_release_workflow_uploads_sha_bound_test_evidence() -> None:
    release = Path(".github/workflows/release.yml").read_text(encoding="utf-8")
    assert "Run isolated test suite" in release
    assert "Generate exact-commit release test evidence" in release
    assert "mutaui-release-test-evidence-${{ matrix.os }}" in release
    assert "test-results/evidence.json" in release
    assert "test-results/acceptance.md" in release
