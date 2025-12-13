#!/usr/bin/env python3
"""
Resize all slot icons in the database from 1024x1024 to 256x256 to reduce payload size.

Usage:
    python bot/tools/resize_slot_icons.py [--dry-run]
"""

import sys
import os
import base64
from io import BytesIO
from PIL import Image

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from utils.session import get_session
from utils.models import UserModel, CharacterModel

TARGET_SIZE = 256


def resize_icon_b64(icon_b64: str) -> str:
    """Resize a base64-encoded icon to 256x256."""
    try:
        # Decode base64
        icon_bytes = base64.b64decode(icon_b64)

        # Open image
        img = Image.open(BytesIO(icon_bytes))
        original_size = img.size

        # Skip if already the target size
        if img.size == (TARGET_SIZE, TARGET_SIZE):
            return icon_b64

        # Resize to 256x256 using high-quality LANCZOS resampling
        resized_img = img.resize((TARGET_SIZE, TARGET_SIZE), Image.Resampling.LANCZOS)

        # Save back to bytes
        output = BytesIO()
        original_format = img.format or "PNG"
        resized_img.save(output, format=original_format, optimize=True)
        resized_bytes = output.getvalue()

        # Encode back to base64
        resized_b64 = base64.b64encode(resized_bytes).decode("utf-8")

        original_kb = len(icon_b64) / 1024
        resized_kb = len(resized_b64) / 1024
        reduction = (1 - resized_kb / original_kb) * 100

        print(
            f"  Resized from {original_size} ({original_kb:.1f} KB) to "
            f"{TARGET_SIZE}x{TARGET_SIZE} ({resized_kb:.1f} KB) - {reduction:.1f}% reduction"
        )

        return resized_b64
    except Exception as e:
        print(f"  ERROR resizing icon: {e}")
        return icon_b64  # Return original on error


def resize_user_icons(dry_run: bool = False):
    """Resize all user slot icons."""
    print("=" * 80)
    print("Resizing user slot icons")
    print("=" * 80)

    with get_session() as session:
        # Get all users with slot icons
        users = session.query(UserModel).filter(UserModel.slot_iconb64.isnot(None)).all()
        users_data = [(u.user_id, u.display_name, u.slot_iconb64) for u in users]

    print(f"Found {len(users_data)} users with slot icons")

    total_saved = 0

    for user_id, display_name, icon_b64 in users_data:
        print(f"\nProcessing user {user_id} ({display_name})...")
        original_size = len(icon_b64)

        resized_b64 = resize_icon_b64(icon_b64)
        resized_size = len(resized_b64)

        saved = original_size - resized_size
        total_saved += saved

        if not dry_run:
            with get_session(commit=True) as session:
                user = session.query(UserModel).filter(UserModel.user_id == user_id).first()
                if user:
                    user.slot_iconb64 = resized_b64
            print(f"  ✓ Updated user {user_id}")
        else:
            print(f"  [DRY RUN] Would update user {user_id}")

    print(f"\n{'=' * 80}")
    print(f"Total space saved for users: {total_saved / (1024 * 1024):.2f} MB")
    print(f"{'=' * 80}\n")


def resize_character_icons(dry_run: bool = False):
    """Resize all character slot icons."""
    print("=" * 80)
    print("Resizing character slot icons")
    print("=" * 80)

    with get_session() as session:
        # Get all characters with slot icons
        characters = (
            session.query(CharacterModel).filter(CharacterModel.slot_iconb64.isnot(None)).all()
        )
        chars_data = [(c.id, c.name, c.slot_iconb64) for c in characters]

    print(f"Found {len(chars_data)} characters with slot icons")

    total_saved = 0

    for char_id, char_name, icon_b64 in chars_data:
        print(f"\nProcessing character {char_id} ({char_name})...")
        original_size = len(icon_b64)

        resized_b64 = resize_icon_b64(icon_b64)
        resized_size = len(resized_b64)

        saved = original_size - resized_size
        total_saved += saved

        if not dry_run:
            with get_session(commit=True) as session:
                char = session.query(CharacterModel).filter(CharacterModel.id == char_id).first()
                if char:
                    char.slot_iconb64 = resized_b64
            print(f"  ✓ Updated character {char_id}")
        else:
            print(f"  [DRY RUN] Would update character {char_id}")

    print(f"\n{'=' * 80}")
    print(f"Total space saved for characters: {total_saved / (1024 * 1024):.2f} MB")
    print(f"{'=' * 80}\n")


def resize_claim_icon(dry_run: bool = False):
    """Resize the claim icon file."""
    print("=" * 80)
    print("Resizing claim icon file")
    print("=" * 80)

    claim_icon_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "data", "slots", "claim_icon.png"
    )

    if not os.path.exists(claim_icon_path):
        print(f"Claim icon not found at {claim_icon_path}")
        return

    try:
        # Read the file
        with open(claim_icon_path, "rb") as f:
            icon_bytes = f.read()

        # Open and check size
        img = Image.open(BytesIO(icon_bytes))
        original_size = img.size
        original_kb = len(icon_bytes) / 1024

        print(f"Current size: {original_size} ({original_kb:.1f} KB)")

        if img.size == (TARGET_SIZE, TARGET_SIZE):
            print(f"Claim icon already {TARGET_SIZE}x{TARGET_SIZE}, no resize needed")
            return

        # Resize
        resized_img = img.resize((TARGET_SIZE, TARGET_SIZE), Image.Resampling.LANCZOS)

        # Save to bytes
        output = BytesIO()
        resized_img.save(output, format="PNG", optimize=True)
        resized_bytes = output.getvalue()

        resized_kb = len(resized_bytes) / 1024
        reduction = (1 - resized_kb / original_kb) * 100

        print(
            f"Resized to {TARGET_SIZE}x{TARGET_SIZE} ({resized_kb:.1f} KB) - {reduction:.1f}% reduction"
        )

        if not dry_run:
            # Write back to file
            with open(claim_icon_path, "wb") as f:
                f.write(resized_bytes)
            print(f"✓ Updated claim icon file")
        else:
            print(f"[DRY RUN] Would update claim icon file")

    except Exception as e:
        print(f"Error processing claim icon: {e}")


def main():
    dry_run = "--dry-run" in sys.argv

    if dry_run:
        print("🔍 DRY RUN MODE - No changes will be made")
        print("")

    print("=" * 80)
    print(f"Resizing Slot Icons to {TARGET_SIZE}x{TARGET_SIZE}")
    print("=" * 80)
    print("")

    # Resize user icons
    resize_user_icons(dry_run=dry_run)

    # Resize character icons
    resize_character_icons(dry_run=dry_run)

    # Resize claim icon file
    resize_claim_icon(dry_run=dry_run)

    print("\n" + "=" * 80)
    if dry_run:
        print("DRY RUN COMPLETE - Run without --dry-run to apply changes")
    else:
        print("✓ ALL SLOT ICONS RESIZED SUCCESSFULLY")
    print("=" * 80)


if __name__ == "__main__":
    main()
