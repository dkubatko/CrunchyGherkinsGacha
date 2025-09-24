import os
import hmac
import hashlib
import base64
import json
import logging
from typing import Optional, Dict, Any
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)


class EncoderUtil:
    """Utility class for encoding and decoding secure data for miniapp communication."""

    def __init__(self):
        self.server_secret = os.getenv("SERVER_SECRET")
        if not self.server_secret:
            logger.error("SERVER_SECRET not found in environment variables")

    def encode_data(self, data: Dict[str, Any]) -> Optional[str]:
        """Encode a dictionary with SERVER_SECRET for secure miniapp communication.

        Args:
            data: Dictionary containing data to encode

        Returns:
            Base64 URL-safe encoded string containing signed data, or None if encoding fails
        """
        if not self.server_secret:
            logger.error("Cannot encode data: SERVER_SECRET not available")
            return None

        try:
            # Convert data to JSON string
            data_json = json.dumps(data, separators=(",", ":"))

            # Create HMAC signature
            signature = hmac.new(
                self.server_secret.encode("utf-8"), data_json.encode("utf-8"), hashlib.sha256
            ).hexdigest()

            # Combine data and signature
            signed_data = {"data": data, "signature": signature}
            signed_json = json.dumps(signed_data, separators=(",", ":"))

            # Base64 encode for URL safety
            encoded = base64.urlsafe_b64encode(signed_json.encode("utf-8")).decode("utf-8")

            return encoded
        except Exception as e:
            logger.error(f"Error encoding data: {e}")
            return None

    def decode_data(self, encoded_data: str) -> Optional[Dict[str, Any]]:
        """Decode and verify data from the miniapp.

        Args:
            encoded_data: Base64 URL-safe encoded string containing signed data

        Returns:
            Dictionary containing the original data if valid, None otherwise
        """
        if not self.server_secret:
            logger.error("Cannot decode data: SERVER_SECRET not available")
            return None

        try:
            # Base64 decode
            decoded_json = base64.urlsafe_b64decode(encoded_data.encode("utf-8")).decode("utf-8")
            signed_data = json.loads(decoded_json)

            # Extract data and signature
            data = signed_data.get("data")
            signature = signed_data.get("signature")

            if not data or not signature:
                logger.warning("Missing data or signature in encoded data")
                return None

            # Recreate the signature to verify
            data_json = json.dumps(data, separators=(",", ":"))
            expected_signature = hmac.new(
                self.server_secret.encode("utf-8"), data_json.encode("utf-8"), hashlib.sha256
            ).hexdigest()

            # Verify signature
            if not hmac.compare_digest(signature, expected_signature):
                logger.warning("Invalid signature in encoded data")
                return None

            return data
        except Exception as e:
            logger.error(f"Error decoding data: {e}")
            return None
