"""Set icon repository for storing/retrieving aspect set slot icons.

Mirrors the CardImageModel/AspectImageModel pattern — images stored in a
separate table (``set_icons``) to avoid overhead on large set queries.
"""

from __future__ import annotations

import base64
import logging
from typing import Dict, Optional

from sqlalchemy.orm import Session

from settings.constants import CURRENT_SEASON
from utils.models import SetIconModel
from utils.session import with_session

logger = logging.getLogger(__name__)


@with_session
def get_icon(
    set_id: int,
    season_id: Optional[int] = None,
    *,
    session: Session,
) -> Optional[bytes]:
    """Return raw icon bytes for a set, or ``None`` if not found."""
    sid = season_id if season_id is not None else CURRENT_SEASON
    row = (
        session.query(SetIconModel)
        .filter(SetIconModel.set_id == set_id, SetIconModel.season_id == sid)
        .first()
    )
    return row.icon if row else None


@with_session
def get_icon_b64(
    set_id: int,
    season_id: Optional[int] = None,
    *,
    session: Session,
) -> Optional[str]:
    """Return base64-encoded icon string for a set, or ``None``."""
    raw = get_icon(set_id, season_id, session=session)
    if raw is None:
        return None
    return base64.b64encode(raw).decode("utf-8")


@with_session(commit=True)
def upsert_icon(
    set_id: int,
    season_id: int,
    icon_bytes: bytes,
    *,
    session: Session,
) -> None:
    """Insert or update the slot icon for a set.

    Ensures stored bytes are always JPEG.
    """
    from utils.image import ImageUtil

    icon_bytes = ImageUtil.to_jpeg(icon_bytes)

    row = (
        session.query(SetIconModel)
        .filter(SetIconModel.set_id == set_id, SetIconModel.season_id == season_id)
        .first()
    )
    if row:
        row.icon = icon_bytes
    else:
        session.add(
            SetIconModel(set_id=set_id, season_id=season_id, icon=icon_bytes)
        )
    logger.info("Upserted slot icon for set %s (season %s)", set_id, season_id)


@with_session
def get_all_icons_b64(
    season_id: Optional[int] = None,
    *,
    session: Session,
) -> Dict[int, str]:
    """Return ``{set_id: base64_icon}`` for every set in *season_id*."""
    sid = season_id if season_id is not None else CURRENT_SEASON
    rows = (
        session.query(SetIconModel)
        .filter(SetIconModel.season_id == sid)
        .all()
    )
    return {
        row.set_id: base64.b64encode(row.icon).decode("utf-8") for row in rows
    }


@with_session(commit=True)
def delete_icon(
    set_id: int,
    season_id: Optional[int] = None,
    *,
    session: Session,
) -> bool:
    """Delete the slot icon for a set. Returns ``True`` if a row was removed."""
    sid = season_id if season_id is not None else CURRENT_SEASON
    deleted = (
        session.query(SetIconModel)
        .filter(SetIconModel.set_id == set_id, SetIconModel.season_id == sid)
        .delete()
    )
    return deleted > 0
