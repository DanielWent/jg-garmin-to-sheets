"""Garmin Connect API client wrapper."""

from typing import Any, Dict, List, Optional
import logging
from garminconnect import Garmin, GarminConnectAuthenticationError, GarminConnectConnectionError

from src.exceptions import GarminAuthException, GarminDataException

logger = logging.getLogger(__name__)


class GarminClient:
    """Wrapper client around the garminconnect library."""

    def __init__(
        self,
        email: Optional[str] = None,
        password: Optional[str] = None,
        token_store: Optional[str] = None,
    ):
        self.email = email
        self.password = password
        self.token_store = token_store
        self.client: Optional[Garmin] = None

    def login(self) -> None:
        """Authenticate with Garmin Connect via stored tokens or credentials."""
        try:
            if self.token_store:
                logger.info("Authenticating with Garmin Connect using token store")
                self.client = Garmin()
                self.client.login(self.token_store)
            elif self.email and self.password:
                logger.info(f"Authenticating with Garmin Connect for user {self.email}")
                self.client = Garmin(self.email, self.password)
                self.client.login()
            else:
                raise GarminAuthException("Missing Garmin credentials or token store.")
        except GarminConnectAuthenticationError as e:
            raise GarminAuthException(f"Garmin authentication failed: {e}") from e
        except Exception as e:
            raise GarminConnectionException(f"Failed to connect to Garmin: {e}") from e

    def get_user_summary(self, date_str: str) -> Dict[str, Any]:
        """
        Fetch daily user summary JSON including steps, active calories, and intensity minutes.
        """
        self._ensure_logged_in()
        try:
            return self.client.get_user_summary(date_str) or {}
        except Exception as e:
            logger.debug(f"Could not retrieve user summary for {date_str}: {e}")
            return {}

    def get_sleep_data(self, date_str: str) -> Dict[str, Any]:
        """Fetch sleep metrics JSON for a given date."""
        self._ensure_logged_in()
        try:
            return self.client.get_sleep_data(date_str) or {}
        except Exception as e:
            logger.debug(f"Could not retrieve sleep data for {date_str}: {e}")
            return {}

    def get_stress_data(self, date_str: str) -> Dict[str, Any]:
        """Fetch stress metrics JSON for a given date."""
        self._ensure_logged_in()
        try:
            return self.client.get_all_day_stress(date_str) or {}
        except Exception as e:
            logger.debug(f"Could not retrieve stress data for {date_str}: {e}")
            return {}

    def get_body_battery(self, date_str: str) -> List[Dict[str, Any]]:
        """Fetch body battery JSON records for a given date."""
        self._ensure_logged_in()
        try:
            return self.client.get_body_battery(date_str) or []
        except Exception as e:
            logger.debug(f"Could not retrieve body battery data for {date_str}: {e}")
            return []

    def get_activities(self, start_date_str: str, end_date_str: str) -> List[Dict[str, Any]]:
        """Fetch list of activities between two dates."""
        self._ensure_logged_in()
        try:
            return self.client.get_activities_by_date(start_date_str, end_date_str) or []
        except Exception as e:
            raise GarminDataException(f"Failed to get activities: {e}") from e

    def _ensure_logged_in(self) -> None:
        """Validate client login state."""
        if not self.client:
            self.login()
