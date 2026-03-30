"""Convert existing PNG slot icons (user + character) to JPEG.

One-time migration script. Finds all slot_icon columns that contain PNG data
and re-encodes them as JPEG using ImageUtil.to_jpeg().

Usage:
    python bot/tools/convert_slot_icons_to_jpeg.py [--dry-run]
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv(dotenv_path=PROJECT_ROOT / ".env", override=False)

from PIL import Image  # noqa: E402
import io  # noqa: E402

from utils.image import ImageUtil  # noqa: E402
from utils.session import get_session  # noqa: E402
from utils.models import UserModel, CharacterModel  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def _detect_format(data: bytes) -> str:
    img = Image.open(io.BytesIO(data))
    return img.format or "UNKNOWN"


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert PNG slot icons to JPEG.")
    parser.add_argument("--dry-run", action="store_true", help="Report without modifying.")
    args = parser.parse_args()

    converted = 0
    skipped = 0

    with get_session(commit=not args.dry_run) as session:
        # Users
        users = session.query(UserModel).filter(UserModel.slot_icon.isnot(None)).all()
        for u in users:
            fmt = _detect_format(u.slot_icon)
            if fmt == "JPEG":
                logger.info("  [skip] user %s — already JPEG", u.user_id)
                skipped += 1
                continue
            if args.dry_run:
                logger.info("  [dry-run] user %s — %s → would convert", u.user_id, fmt)
                converted += 1
                continue
            original_size = len(u.slot_icon)
            u.slot_icon = ImageUtil.to_jpeg(u.slot_icon)
            logger.info(
                "  [convert] user %s — %s → JPEG (%d → %d bytes)",
                u.user_id, fmt, original_size, len(u.slot_icon),
            )
            converted += 1

        # Characters
        chars = session.query(CharacterModel).filter(CharacterModel.slot_icon.isnot(None)).all()
        for c in chars:
            fmt = _detect_format(c.slot_icon)
            if fmt == "JPEG":
                logger.info("  [skip] char %s (%s) — already JPEG", c.id, c.name)
                skipped += 1
                continue
            if args.dry_run:
                logger.info("  [dry-run] char %s (%s) — %s → would convert", c.id, c.name, fmt)
                converted += 1
                continue
            original_size = len(c.slot_icon)
            c.slot_icon = ImageUtil.to_jpeg(c.slot_icon)
            logger.info(
                "  [convert] char %s (%s) — %s → JPEG (%d → %d bytes)",
                c.id, c.name, fmt, original_size, len(c.slot_icon),
            )
            converted += 1

    logger.info("Done. converted=%d  skipped=%d", converted, skipped)


if __name__ == "__main__":
    main()
