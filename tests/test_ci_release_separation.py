"""PR CI must not contain code-signing credentials or unreachable release steps."""

from pathlib import Path


def test_pull_request_workflow_does_not_request_release_secrets() -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "contents: read" in workflow
    assert "id-token: write" not in workflow
    assert "attestations: write" not in workflow
    assert "APPLE_CERTIFICATE_BASE64" not in workflow
    assert "APPLE_NOTARY_KEY_BASE64" not in workflow
    assert "WINDOWS_SIGNING_CERT" not in workflow
    assert "notarytool" not in workflow
    assert "refs/tags/" not in workflow


def test_release_workflow_owns_signing_and_provenance() -> None:
    release = Path(".github/workflows/release.yml").read_text(encoding="utf-8")
    assert "APPLE_CERTIFICATE_BASE64" in release
    assert "WINDOWS_SIGNING_CERT_BASE64" in release
    assert "notarytool submit" in release
    assert "id-token: write" in release
    assert "actions/attest" in release
