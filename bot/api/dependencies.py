"""
Authentication dependencies for FastAPI endpoints.

This module provides FastAPI dependency functions for validating Telegram WebApp
authorization and verifying user identity.
"""

import hmac
import hashlib
import json
import logging
import time
import urllib.parse
from typing import Dict, Any, Optional

from fastapi import Header, HTTPException

from api.config import TELEGRAM_TOKEN
from utils.models import ChatModel
from utils.session import get_session
from utils.services import admin_auth_service

logger = logging.getLogger(__name__)


def validate_telegram_init_data(init_data: str) -> Optional[Dict[str, Any]]:
    """
    Validate Telegram WebApp init data according to:
    https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app

    Args:
        init_data: URL-encoded init data from Telegram WebApp

    Returns:
        Dictionary with parsed and validated data, or None if validation fails
    """
    if not TELEGRAM_TOKEN:
        logger.error("Bot token not available for init data validation")
        return None

    try:
        # Parse URL-encoded data
        parsed_data = urllib.parse.parse_qs(init_data)

        # Extract hash and other data
        received_hash = parsed_data.get("hash", [None])[0]
        if not received_hash:
            logger.warning("No hash found in init data")
            return None

        # Remove hash from data for validation
        data_check_string_parts = []
        for key in sorted(parsed_data.keys()):
            if key != "hash":
                values = parsed_data[key]
                for value in values:
                    data_check_string_parts.append(f"{key}={value}")

        data_check_string = "\n".join(data_check_string_parts)

        # Create secret key from bot token
        secret_key = hmac.new(b"WebAppData", TELEGRAM_TOKEN.encode(), hashlib.sha256).digest()

        # Calculate expected hash
        expected_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

        # Verify hash
        if not hmac.compare_digest(received_hash, expected_hash):
            logger.warning("Init data hash validation failed")
            return None

        # Parse user data if present
        user_data = None
        if "user" in parsed_data:
            try:
                user_data = json.loads(parsed_data["user"][0])
            except (json.JSONDecodeError, IndexError):
                logger.warning("Failed to parse user data from init data")
                return None

        # Parse auth_date and check if not too old (optional, but recommended)
        auth_date = parsed_data.get("auth_date", [None])[0]
        if auth_date:
            try:
                auth_timestamp = int(auth_date)
                current_timestamp = int(time.time())
                # Check if auth_date is not older than 24 hours
                if current_timestamp - auth_timestamp > 24 * 60 * 60:
                    logger.warning("Init data is too old (older than 24 hours)")
                    return None
            except (ValueError, TypeError):
                logger.warning("Invalid auth_date in init data")
                return None

        return {
            "user": user_data,
            "auth_date": auth_date,
            "query_id": parsed_data.get("query_id", [None])[0],
            "chat_instance": parsed_data.get("chat_instance", [None])[0],
            "chat_type": parsed_data.get("chat_type", [None])[0],
            "start_param": parsed_data.get("start_param", [None])[0],
        }

    except Exception as e:
        logger.error(f"Error validating init data: {e}")
        return None


def extract_init_data_from_header(authorization: Optional[str]) -> Optional[str]:
    """Extract init data from Authorization header."""
    if not authorization:
        return None

    # Handle both "Bearer <initdata>" and direct initdata formats
    if authorization.startswith("Bearer "):
        return authorization[7:]
    elif authorization.startswith("tma "):  # Telegram Mini App prefix
        return authorization[4:]
    else:
        return authorization


async def get_validated_user(
    authorization: Optional[str] = Header(None, alias="Authorization")
) -> Dict[str, Any]:
    """
    FastAPI dependency that validates Telegram mini app authorization.
    Returns the validated user data dictionary.
    """
    if not authorization:
        logger.warning("No authorization header provided")
        raise HTTPException(status_code=401, detail="Authorization header required")

    init_data = extract_init_data_from_header(authorization)
    if not init_data:
        logger.warning("No init data found in authorization header")
        raise HTTPException(status_code=401, detail="Invalid authorization format")

    validated_data = validate_telegram_init_data(init_data)
    if not validated_data or not validated_data.get("user"):
        logger.warning("Invalid Telegram init data provided")
        raise HTTPException(status_code=401, detail="Invalid or expired Telegram data")

    return validated_data


async def verify_user_match(request_user_id: int, validated_user: Dict[str, Any]) -> Dict[str, Any]:
    """
    Helper to verify that the authenticated user matches the request user_id.
    Returns the validated user data if match is successful.
    """
    user_data: Dict[str, Any] = validated_user.get("user") or {}
    auth_user_id = user_data.get("id")

    if not isinstance(auth_user_id, int):
        logger.warning("Missing or invalid user_id in init data")
        raise HTTPException(status_code=400, detail="Invalid user data in init data")

    if auth_user_id != request_user_id:
        logger.warning(f"User ID mismatch (auth: {auth_user_id}, request: {request_user_id})")
        raise HTTPException(status_code=403, detail="Unauthorized request")

    return validated_user


async def validate_chat_exists(chat_id: str) -> None:
    """
    Validate that a chat_id exists in the chats table.
    Raises 404 if no membership rows exist for the given chat_id.
    """
    with get_session() as session:
        exists = session.query(ChatModel.chat_id).filter(ChatModel.chat_id == chat_id).first()
    if not exists:
        logger.warning(f"Request with non-existent chat_id: {chat_id}")
        raise HTTPException(status_code=404, detail="Chat not found")


async def validate_user_in_chat(user_id: int, chat_id: str) -> None:
    """
    Validate that a chat exists AND the user is enrolled in it.
    Raises 404 if the chat doesn't exist, 403 if the user is not a member.
    """
    with get_session() as session:
        chat_exists = session.query(ChatModel.chat_id).filter(ChatModel.chat_id == chat_id).first()
        if not chat_exists:
            logger.warning(f"Request with non-existent chat_id: {chat_id}")
            raise HTTPException(status_code=404, detail="Chat not found")

        membership = (
            session.query(ChatModel)
            .filter(ChatModel.chat_id == chat_id, ChatModel.user_id == user_id)
            .first()
        )
    if not membership:
        logger.warning(f"User {user_id} not enrolled in chat {chat_id}")
        raise HTTPException(status_code=403, detail="User not enrolled in this chat")


# ── Admin dashboard auth ─────────────────────────────────────────────────────


async def get_admin_user(
    authorization: Optional[str] = Header(None, alias="Authorization"),
) -> Dict[str, Any]:
    """FastAPI dependency that validates an admin JWT from ``Authorization: Bearer <token>``.

    Returns the decoded JWT payload (contains ``sub``, ``username``, ``iat``, ``exp``).
    Raises 401 if the header is missing, malformed, or the token is invalid/expired.
    """
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header required")

    # Accept "Bearer <token>" format
    if authorization.startswith("Bearer "):
        token = authorization[7:]
    else:
        raise HTTPException(
            status_code=401, detail="Invalid authorization format — expected 'Bearer <token>'"
        )

    payload = admin_auth_service.decode_jwt(token)
    if payload is None:
        raise HTTPException(status_code=401, detail="Invalid or expired admin token")

    return payload
