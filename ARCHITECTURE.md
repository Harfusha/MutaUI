# Architecture

**Data:** The local `MutagenClient` calls only the native CLI (`sync list --template`, `forward list --template`). Exported native endpoint models are used for both sides of a sync. Host grouping is string-based and does not open its own SSH, DNS, or HTTP connections.

**Performance:** `QThreadPool` handles CLI calls and process measurements; history uses a separate SQLite writer, history cache, and cached graph geometry. `AdaptivePolling` changes only the GUI status refresh interval in response to detected changes or Mutagen's current phase. It does not change the frequency of actual sync cycles.

**Native watch profiles:** A whitelist of `sync create` parameters: `portable`, `force-poll`, `no-watch`, and `watch-polling-interval`. They cannot change running sessions. Settings for existing sessions are local GUI preferences only (notes and notifications); native values are read-only.

**Qt:** Session details and settings use `QScrollArea` and layouts with a minimum size based on their contents. The circular indicator draws small text in pixel units. Tables have specific empty states. The GUI smoke test checks sync counts against the selected server and does not assume a fixed group order.

**EXE:** Build scripts run unit tests and the Qt smoke test on Windows before the PyInstaller build. Python/PySide6 is not needed to run the finished EXE; the Mutagen CLI remains an external dependency.
