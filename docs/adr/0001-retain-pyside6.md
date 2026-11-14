# ADR-0001: Retain PySide6

Status: accepted for incremental migration.

Keep the existing PySide6 Essentials desktop application and Windows packaging while modularizing `app.py` in small steps. This preserves the working interface and avoids a risky framework rewrite. Reconsider only with measured release and accessibility evidence.
