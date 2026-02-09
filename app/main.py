from __future__ import annotations

import logging

from app.bot import build_app
from app.config import settings


def configure_logging() -> None:
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


def main() -> None:
    configure_logging()
    app = build_app(settings.telegram_bot_token)
    app.run_polling(close_loop=False)


if __name__ == "__main__":
    main()
