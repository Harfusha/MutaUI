# ADR-0005: Platform support is capability-gated

Status: accepted.

Keep OS-specific paths, notifications, startup, tray and file-manager integration behind platform adapters. Query installed Mutagen capabilities. Show unsupported features with a reason; advertise platform support only after native CI and packaged smoke pass.
