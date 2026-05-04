# Sahayak 1092 – Backend Package
import sys

# Fix Windows console encoding for Unicode characters (emoji, etc.)
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
