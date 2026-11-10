"""Run the shared engine from a linked Skill directory without installing packages."""
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from regression_guard.cli import main  # noqa: E402

raise SystemExit(main())
