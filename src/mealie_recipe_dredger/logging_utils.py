import logging
import os
import sys


def configure_logging(logger_name: str = "dredger") -> logging.Logger:
    level = os.getenv("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    # Keep dependency debug chatter (charset auto-detection) from drowning actionable logs.
    logging.getLogger("charset_normalizer").setLevel(logging.WARNING)
    logging.getLogger("chardet").setLevel(logging.WARNING)

    return logging.getLogger(logger_name)
