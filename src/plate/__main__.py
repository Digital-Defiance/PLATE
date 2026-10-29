"""Enable `python -m plate` (used by the CLI's renderer re-exec on macOS)."""
from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
