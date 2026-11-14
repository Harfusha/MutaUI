# Conflict diff copies

PR-030 connects a fetched remote SSH conflict copy with a copied local-side
file when the opposite endpoint is local. Both files are placed in the remote
inspection's private temporary directory; the local source is never passed to
the external tool. The local copy is bounded, hashable, checked for a stable
file snapshot, and marked read-only. The external tool is selected explicitly
for each compare and receives exactly two file arguments through Qt's process
API; no shell or user-provided command string is used.

Temporary copies stay alive until the diff process exits or the inspector closes.
Two-remote-endpoint diff is not exposed yet. Manual resolution, remote writes,
and conflict clearing remain disabled.
