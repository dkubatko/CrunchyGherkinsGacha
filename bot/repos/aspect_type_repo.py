"""Repository for aspect type CRUD operations."""

from datetime import datetime, timezone
from typing import List, Optional, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from utils.models import AspectDefinitionModel, AspectTypeModel
from utils.session import with_session


@with_session
def get_all_types(*, session: Session) -> List[AspectTypeModel]:
    """Return all aspect types ordered by name."""
    return (
        session.query(AspectTypeModel)
        .order_by(AspectTypeModel.name)
        .all()
    )


@with_session
def get_all_types_with_counts(
    *, session: Session
) -> List[Tuple[AspectTypeModel, int]]:
    """Return all aspect types and their usage count in a single GROUP BY query."""
    rows = (
        session.query(
            AspectTypeModel,
            func.count(AspectDefinitionModel.id),
        )
        .outerjoin(
            AspectDefinitionModel,
            AspectDefinitionModel.type_id == AspectTypeModel.id,
        )
        .group_by(AspectTypeModel.id)
        .order_by(AspectTypeModel.name)
        .all()
    )
    return [(t, int(c)) for t, c in rows]


@with_session
def get_aspects_for_type(
    type_id: int, *, session: Session
) -> List[AspectDefinitionModel]:
    """Return all aspect definitions referencing this type, with set eagerly loaded.

    Ordered by season (newest first), then set id, rarity, name.
    """
    return (
        session.query(AspectDefinitionModel)
        .options(joinedload(AspectDefinitionModel.aspect_set))
        .filter(AspectDefinitionModel.type_id == type_id)
        .order_by(
            AspectDefinitionModel.season_id.desc(),
            AspectDefinitionModel.set_id,
            AspectDefinitionModel.rarity,
            AspectDefinitionModel.name,
        )
        .all()
    )


@with_session
def get_type_by_id(type_id: int, *, session: Session) -> Optional[AspectTypeModel]:
    """Return a single aspect type by ID, or None."""
    return (
        session.query(AspectTypeModel)
        .filter(AspectTypeModel.id == type_id)
        .first()
    )


@with_session(commit=True)
def create_type(
    name: str, description: Optional[str] = None, *, session: Session
) -> AspectTypeModel:
    """Create a new aspect type and return the ORM object."""
    obj = AspectTypeModel(
        name=name,
        description=description,
        created_at=datetime.now(timezone.utc),
    )
    session.add(obj)
    session.flush()
    return obj


@with_session(commit=True)
def update_type(
    type_id: int,
    name: Optional[str] = None,
    description: object = None,
    *,
    session: Session,
) -> Optional[AspectTypeModel]:
    """Update an existing aspect type.

    Pass ``description=""`` to clear it.  ``None`` means "don't change".
    """
    obj = (
        session.query(AspectTypeModel)
        .filter(AspectTypeModel.id == type_id)
        .first()
    )
    if obj is None:
        return None
    if name is not None:
        obj.name = name
    if description is not None:
        obj.description = description or None
    session.flush()
    return obj


@with_session
def get_usage_count(type_id: int, *, session: Session) -> int:
    """Return the number of aspect definitions referencing this type."""
    return (
        session.query(func.count())
        .select_from(AspectDefinitionModel)
        .filter(AspectDefinitionModel.type_id == type_id)
        .scalar()
    )


@with_session(commit=True)
def delete_type(type_id: int, *, session: Session) -> Tuple[bool, str]:
    """Delete an aspect type. Returns (success, message).

    Fails if any aspect definitions still reference this type.
    """
    obj = (
        session.query(AspectTypeModel)
        .filter(AspectTypeModel.id == type_id)
        .first()
    )
    if obj is None:
        return False, "not_found"

    count = get_usage_count(type_id, session=session)
    if count > 0:
        return False, f"Cannot delete: {count} aspect definition(s) still use this type."

    session.delete(obj)
    return True, "Deleted."
