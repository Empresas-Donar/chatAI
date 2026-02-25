import logging
import os
import sys

os.makedirs("logs", exist_ok=True)


def print_progress(current: int, total: int, label: str = "") -> None:
    """Print an inline progress line that updates in place."""
    pct = int(current / total * 100) if total else 0
    bar = "#" * (pct // 5) + "-" * (20 - pct // 5)
    suffix = f"  {label}" if label else ""
    print(f"\r  [{bar}] {pct:3d}%  {current}/{total}{suffix}", end="", flush=True)
    if current == total:
        print()  # newline when done


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        fh = logging.FileHandler(f"logs/{name}.log")
        fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
        logger.addHandler(fh)
        ch = logging.StreamHandler()
        ch.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
        logger.addHandler(ch)
    return logger
