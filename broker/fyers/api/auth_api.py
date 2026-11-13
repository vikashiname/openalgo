import hashlib
import json
import os
from typing import Any, Dict, Optional, Tuple

from utils.httpx_client import get_httpx_client
from utils.logging import get_logger

logger = get_logger(__name__)


def authenticate_broker(request_token: str) -> tuple[str | None, dict[str, Any] | None]:
    """
    Authenticate with FYERS API using request token and return access token with user details.

    Args:
        request_token: The authorization code received from FYERS

    Returns:
        Tuple of (access_token, response_data).
        - access_token: The authentication token if successful, None otherwise
        - response_data: Full response data or error details
    """
    # Initialize response data
    response_data = {"status": "error", "message": "Authentication failed", "data": None}

    # Get environment variables
    broker_api_key = os.getenv("BROKER_API_KEY")
    broker_api_secret = os.getenv("BROKER_API_SECRET")

    # Validate environment variables
    if not broker_api_key or not broker_api_secret:
        error_msg = "Missing BROKER_API_KEY or BROKER_API_SECRET in environment variables"
        logger.error(error_msg)
        response_data["message"] = error_msg
        return None, response_data

    if not request_token:
        error_msg = "No request token provided"
        logger.error(error_msg)
        response_data["message"] = error_msg
        return None, response_data

    # FYERS's endpoint for session token exchange
    url = "https://api-t1.fyers.in/api/v3/validate-authcode"

    try:
        # Generate the checksum as a SHA-256 hash of concatenated api_key and api_secret
        checksum_input = f"{broker_api_key}:{broker_api_secret}"
        app_id_hash = hashlib.sha256(checksum_input.encode("utf-8")).hexdigest()

        # Prepare the request payload
        payload = {
            "grant_type": "authorization_code",
            "appIdHash": app_id_hash,
            "code": request_token,
        }

        headers = {"Content-Type": "application/json", "Accept": "application/json"}

        # Get shared HTTP client with connection pooling
        client = get_httpx_client()

        logger.debug(f"Authenticating with FYERS API at {url} (grant_type={payload['grant_type']})")

        # Make the authentication request
        response = client.post(
            url,
            headers=headers,
            json=payload,
            timeout=30.0,  # Increased timeout for auth requests
        )

        # Process the response
        response.raise_for_status()
        auth_data = response.json()
        logger.debug(f"FYERS auth API response: {json.dumps(auth_data, indent=2)}")

        if auth_data.get("s") == "ok":
            access_token = auth_data.get("access_token")
            if not access_token:
                error_msg = "Authentication succeeded but no access token was returned"
                logger.error(error_msg)
                response_data["message"] = error_msg
                return None, response_data

            # Prepare success response
            response_data.update(
                {
                    "status": "success",
                    "message": "Authentication successful",
                    "data": {
                        "access_token": access_token,
                        "refresh_token": auth_data.get("refresh_token"),
                        "expires_in": auth_data.get("expires_in"),
                    },
                }
            )

            logger.debug("Successfully authenticated with FYERS API")
            return access_token, response_data

        else:
            # Handle API error response
            error_msg = auth_data.get("message", "Authentication failed")
            logger.error(f"FYERS API error: {error_msg}")
            response_data["message"] = f"API error: {error_msg}"
            return None, response_data

    except Exception as e:
        error_msg = f"Authentication failed: {e}"
        logger.exception("Authentication failed due to an unexpected error")
        response_data["message"] = error_msg
        return None, response_data


def renew_broker_token(refresh_token: str, pin: str) -> tuple[str | None, dict[str, Any]]:
    """
    Renew FYERS access token using the stored refresh token and PIN.
    Endpoint: https://api-t1.fyers.in/api/v3/validate-refresh-token

    Args:
        refresh_token: The active refresh token previously received from FYERS
        pin: The user's 4-digit FYERS trading PIN

    Returns:
        Tuple of (access_token, response_data).
        - access_token: Fresh daily authentication token if successful, None otherwise
        - response_data: Full response dictionary
    """
    response_data = {"status": "error", "message": "Token renewal failed", "data": None}

    broker_api_key = os.getenv("BROKER_API_KEY")
    broker_api_secret = os.getenv("BROKER_API_SECRET")

    if not broker_api_key or not broker_api_secret:
        error_msg = "Missing BROKER_API_KEY or BROKER_API_SECRET in environment variables"
        logger.error(error_msg)
        response_data["message"] = error_msg
        return None, response_data

    if not refresh_token:
        error_msg = "No refresh token provided"
        logger.error(error_msg)
        response_data["message"] = error_msg
        return None, response_data

    if not pin:
        error_msg = "No PIN provided"
        logger.error(error_msg)
        response_data["message"] = error_msg
        return None, response_data

    url = "https://api-t1.fyers.in/api/v3/validate-refresh-token"

    try:
        checksum_input = f"{broker_api_key}:{broker_api_secret}"
        app_id_hash = hashlib.sha256(checksum_input.encode("utf-8")).hexdigest()

        payload = {
            "grant_type": "refresh_token",
            "appIdHash": app_id_hash,
            "refresh_token": refresh_token,
            "pin": str(pin).strip(),
        }

        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        client = get_httpx_client()

        logger.debug(f"Renewing FYERS token at {url} (grant_type=refresh_token)")

        response = client.post(
            url,
            headers=headers,
            json=payload,
            timeout=30.0,
        )

        response.raise_for_status()
        auth_data = response.json()
        logger.debug(f"FYERS token renewal response: {json.dumps(auth_data, indent=2)}")

        if auth_data.get("s") in ("ok", "success") or auth_data.get("code") == 200:
            access_token = auth_data.get("access_token")
            if not access_token:
                error_msg = "Renewal succeeded but no access token was returned"
                logger.error(error_msg)
                response_data["message"] = error_msg
                return None, response_data

            response_data.update(
                {
                    "status": "success",
                    "message": "Token renewed successfully",
                    "data": {
                        "access_token": access_token,
                    },
                }
            )
            logger.info("Successfully renewed FYERS access token")
            return access_token, response_data
        else:
            error_msg = auth_data.get("message", "Token renewal failed")
            error_code = auth_data.get("code")
            logger.error(f"FYERS renewal API error ({error_code}): {error_msg}")
            response_data["message"] = f"API error ({error_code}): {error_msg}"
            response_data["code"] = error_code
            return None, response_data

    except Exception as e:
        error_msg = f"Token renewal exception: {e}"
        logger.exception("Token renewal failed due to an unexpected error")
        response_data["message"] = error_msg
        return None, response_data

