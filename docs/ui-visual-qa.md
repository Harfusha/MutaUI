# UI screenshot and visual QA

`gui_capture.py` renders the offline demo and does not connect to or modify a Mutagen daemon. One run captures the pages that are visible in the chosen navigation mode.

Capture one page set with explicit presentation settings:

```powershell
python gui_capture.py ui-preview/light-cs-advanced-1_25x --theme light --language cs --mode advanced --scale 1.25
```

Capture the 16-case pairwise matrix:

```powershell
python scripts/capture_ui_matrix.py ui-preview/matrix
```

The matrix covers every pair of values across dark/light theme, English/Czech, Basic/Advanced mode, and 100/125/150/200% scale. Review the resulting PNGs for clipping, overlap, and unreadable text; generation alone is not a visual or accessibility pass. The Czech interface is still incomplete, so these captures are currently diagnostic and are not approved release screenshots.
