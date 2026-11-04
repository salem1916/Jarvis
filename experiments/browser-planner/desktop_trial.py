"""Launch Jarvis Desktop with the optional planner enabled for this session."""

import os
import site
import sys
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[2]
    base = Path(os.environ.get("JARVIS_BASE_VENV", str(root / ".venv")))
    sys.path.insert(0, str(root / "src"))
    site.addsitedir(str(base / "Lib" / "site-packages"))
    os.environ.setdefault("JARVIS_BROWSER_PLANNER", "grounded")
    os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")
    os.chdir(root)

    from jarvis.ui.desktop import main as desktop_main

    desktop_main(title="JARVIS · Browser Planner Trial")


if __name__ == "__main__":
    main()
