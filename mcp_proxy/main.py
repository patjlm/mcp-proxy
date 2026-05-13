from __future__ import annotations

import asyncio
import sys

from .config import load_config
from .proxy import run_proxy


def main() -> None:
    try:
        config = load_config()
    except ValueError as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        asyncio.run(run_proxy(config))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
