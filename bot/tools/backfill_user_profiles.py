"""Populate display names and profile images for users.

Usage:
    python tools/backfill_user_profiles.py
"""

from __future__ import annotations

import base64
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Ensure project root is on sys.path for module imports
CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv(dotenv_path=PROJECT_ROOT / ".env", override=False)

from settings.constants import BASE_IMAGE_PATH  # noqa: E402
from utils.session import get_session  # noqa: E402
from utils.models import UserModel  # noqa: E402

USERNAME_TO_DISPLAY_NAME = {
    "krypthos": "Daniel",
    "brvsnshn": "Lera",
    "sonyabkim": "Sofia",
    "matulka": "Evgenii",
    "maxelnot": "Sasha",
    "imkht": "Ira",
    "max_zubatov": "Max",
    "gabe_mkh": "Gab",
    "yokocookie": "Dina",
}


def _find_image_path(base_dir: Path, display_name: str) -> Path | None:
    candidates = [
        base_dir / f"{display_name}.jpg",
        base_dir / f"{display_name}.jpeg",
        base_dir / f"{display_name}.JPG",
        base_dir / f"{display_name}.JPEG",
    ]
    for path in candidates:
        if path.exists():
            return path
    return None


def main() -> None:
    base_images_dir = Path(BASE_IMAGE_PATH)
    if not base_images_dir.is_absolute():
        base_images_dir = PROJECT_ROOT / BASE_IMAGE_PATH
    base_images_dir = base_images_dir.resolve()

    updated = 0
    skipped = []

    with get_session(commit=True) as session:
        for username, display_name in USERNAME_TO_DISPLAY_NAME.items():
            image_path = _find_image_path(base_images_dir, display_name)
            if image_path is None:
                skipped.append((username, display_name))
                continue

            with image_path.open("rb") as img_file:
                image_b64 = base64.b64encode(img_file.read()).decode("utf-8")

            user = session.query(UserModel).filter(UserModel.username == username).first()
            if user:
                user.display_name = display_name
                user.profile_imageb64 = image_b64
                updated += 1

    print(f"Updated {updated} users with display names and images.")
    if skipped:
        print("Skipped the following users (image not found):")
        for username, display_name in skipped:
            print(f"  - {username} (expected {display_name}.jpg/.jpeg)")


if __name__ == "__main__":
    main()
