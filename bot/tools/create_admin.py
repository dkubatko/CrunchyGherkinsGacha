"""Create an admin user for the modifier management dashboard.

Usage:
    python tools/create_admin.py --username admin --telegram-user-id 123456789

You will be prompted for a password interactively (not echoed to the terminal).
The password is bcrypt-hashed before storage.
"""

from __future__ import annotations

import argparse
import datetime
import getpass
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

# Ensure project root is on sys.path for module imports
CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv(dotenv_path=PROJECT_ROOT / ".env", override=False)

# Must import after dotenv loading so database is configured
from utils import database  # noqa: E402
from utils.models import AdminUserModel  # noqa: E402
from utils.session import get_session  # noqa: E402
from utils.services.admin_auth_service import hash_password  # noqa: E402

# Initialize database (uses default pool settings)
database.initialize_database()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create an admin user for the modifier management dashboard."
    )
    parser.add_argument(
        "--username",
        required=True,
        help="Unique login username for the admin account",
    )
    parser.add_argument(
        "--telegram-user-id",
        type=int,
        required=True,
        help="Telegram numeric user ID for OTP delivery (find via @userinfobot)",
    )

    args = parser.parse_args()

    # Prompt for password (hidden input)
    password = getpass.getpass("Enter password: ")
    if not password:
        logger.error("Password cannot be empty")
        sys.exit(1)

    confirm = getpass.getpass("Confirm password: ")
    if password != confirm:
        logger.error("Passwords do not match")
        sys.exit(1)

    # Check for existing admin with this username
    with get_session() as session:
        existing = (
            session.query(AdminUserModel).filter(AdminUserModel.username == args.username).first()
        )
        if existing:
            logger.error("Admin user '%s' already exists (id=%s)", args.username, existing.id)
            sys.exit(1)

    # Create the admin user
    hashed = hash_password(password)
    now = datetime.datetime.utcnow().isoformat()

    with get_session(commit=True) as session:
        admin = AdminUserModel(
            username=args.username,
            password_hash=hashed,
            telegram_user_id=args.telegram_user_id,
            created_at=now,
        )
        session.add(admin)
        session.flush()
        logger.info(
            "Admin user created: id=%s username='%s' telegram_user_id=%s",
            admin.id,
            admin.username,
            admin.telegram_user_id,
        )

    print(f"\n✅ Admin user '{args.username}' created successfully.")
    print(f"   Telegram user ID: {args.telegram_user_id}")
    print("   You can now log in via the admin dashboard.")


if __name__ == "__main__":
    main()
