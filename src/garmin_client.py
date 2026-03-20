from datetime import date, datetime, timedelta
from typing import Dict, Any, Optional, List
import asyncio
import logging
import json
import garminconnect
import garth
from pathlib import Path
from .exceptions import MFARequiredException
from .config import GarminMetrics
from statistics import mean
from functools import partial

logger = logging.getLogger(__name__)

# Full 21-point percentile scale provided by the ACSM guidelines
PERCENTILES = [1, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70, 75, 80, 85, 90, 95, 99]

NORMATIVE_DATA = {
    'M': {
        25: [26.5, 31.8, 34.7, 36.7, 38.0, 39.0, 39.9, 41.0, 41.7, 42.6, 43.9, 44.8, 45.6, 46.8, 47.5, 48.5, 51.1, 51.8, 54.0, 55.5, 60.5], 
        35: [26.5, 31.2, 33.8, 35.2, 36.7, 37.8, 38.7, 39.5, 40.7, 41.2, 42.4, 43.9, 44.1, 45.3, 46.0, 47.0, 48.3, 50.0, 51.7, 54.1, 58.3], 
        45: [25.1, 29.4, 32.3, 33.8, 34.8, 35.9, 36.7, 37.6, 38.4, 39.5, 40.1, 41.0, 42.4, 43.1, 43.9, 44.9, 46.4, 48.2, 49.6, 52.5, 56.1], 
        55: [22.8, 26.9, 29.4, 30.9, 32.0, 32.8, 33.8, 34.8, 35.5, 36.7, 37.1, 38.1, 39.0, 39.7, 41.0, 41.8, 43.3, 44.6, 46.8, 49.0, 54.0], 
        65: [19.7, 23.6, 25.6, 27.3, 28.7, 29.5, 30.8, 31.6, 32.3, 33.0, 33.8, 34.9, 35.6, 36.7, 37.4, 38.3, 39.6, 41.0, 42.7, 45.7, 51.1], 
        75: [18.2, 20.8, 23.0, 24.6, 25.7, 26.9, 28.0, 28.4, 29.4, 30.1, 30.9, 31.6, 32.4, 33.1, 33.9, 35.2, 36.7, 38.1, 39.5, 43.9, 49.6]  
    },
    'F': {
        25: [23.7, 27.6, 29.5, 30.9, 32.3, 33.0, 34.1, 35.2, 36.1, 36.7, 37.8, 38.5, 39.5, 41.0, 41.1, 42.4, 43.9, 45.3, 46.8, 49.6, 54.5], 
        35: [22.9, 25.9, 28.0, 29.4, 30.9, 32.0, 32.4, 33.8, 34.2, 35.2, 36.7, 36.9, 37.7, 38.5, 39.6, 41.0, 42.4, 43.9, 45.3, 47.4, 52.0], 
        45: [22.2, 25.1, 26.6, 28.2, 29.4, 30.2, 31.1, 32.3, 32.8, 33.8, 34.5, 35.2, 35.9, 36.7, 38.1, 38.6, 39.6, 41.0, 43.1, 45.3, 51.1], 
        55: [20.1, 23.0, 24.6, 25.8, 26.8, 28.0, 28.7, 29.4, 29.9, 30.9, 31.4, 32.3, 32.6, 33.3, 34.2, 35.2, 36.7, 37.0, 38.8, 41.0, 46.1], 
        65: [19.5, 21.8, 23.0, 23.9, 24.6, 25.1, 25.9, 26.6, 27.3, 28.2, 28.8, 29.4, 29.7, 30.9, 31.1, 32.3, 32.7, 34.2, 35.9, 37.8, 42.4], 
        75: [16.8, 19.6, 21.5, 22.2, 23.5, 24.2, 24.7, 25.3, 25.9, 26.7, 27.6, 28.0, 28.1, 29.4, 29.4, 29.8, 30.6, 32.3, 32.5, 37.2, 42.4]  
    }
}

def interp_python(x, xp, fp):
    if x <= xp[0]: return fp[0]
    if x >= xp[-1]: return fp[-1]
    for i in range(len(xp) - 1):
        if xp[i] <= x <= xp[i+1]:
            if xp[i] == xp[i+1]:
                return fp[i]
            weight = (x - xp[i]) / (xp[i+1] - xp[i])
            return fp[i] + weight * (fp[i+1] - fp[i])
    return fp[-1]

def calculate_exact_percentile(age, gender, vo2_max):
    if age is None or gender is None or vo2_max is None:
        return None
        
    gender = gender.upper()
    if gender not in ['M', 'F']:
        if gender == "MALE": gender = "M"
        elif gender == "FEMALE": gender = "F"
        else: return None
        
    data = NORMATIVE_DATA.get(gender)
    if not data: return None
    
    anchors = sorted(data.keys())
    
    if age <= anchors[0]:
        interpolated_thresholds = data[anchors[0]]
    elif age >= anchors[-1]:
        interpolated_thresholds = data[anchors[-1]]
    else:
        for i in range(len(anchors) - 1):
            if anchors[i] <= age < anchors[i+1]:
                lower_anchor = anchors[i]
                upper_anchor = anchors[i+1]
                break
        
        weight = (age - lower_anchor) / (upper_anchor - lower_anchor)
        lower_thresholds = data[lower_anchor]
        upper_thresholds = data[upper_anchor]
        
        interpolated_thresholds = [l * (1 - weight) + u * weight for l, u in zip(lower_thresholds, upper_thresholds)]
    
    exact_percentile = interp_python(vo2_max, interpolated_thresholds, PERCENTILES)
    return round(exact_percentile, 1)

class GarminClient:
    def __init__(self, email: str, password: str, profile_name: str = "default", 
                 manual_name: str = None, manual_dob: str = None, manual_gender: str = None):
        self.email = email
        self.password = password
        self.profile_name = profile_name
        self.manual_name = manual_name
        self.manual_dob = manual_dob
        self.manual_gender = manual_gender
        
        self.session_dir = Path(f"~/.garth/{self.profile_name}").expanduser()
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.token_file = self.session_dir / "tokens.json"
        
        self.client = garminconnect.Garmin(email, password)
        self._authenticated = False
        self.mfa_ticket_dict = None
        self._auth_failed = False
        
        self.user_full_name = None
        self.user_age = None
        self.user_gender = None

    def save_session(self):
        """Saves current Garth OAuth tokens to disk."""
        try:
            with open(self.token_file, "w") as f:
                f.write(self.client.garth.dumps())
            logger.debug(f"Saved session tokens to {self.token_file}")
        except Exception as e:
            logger.error(f"Failed to save session tokens: {e}")

    async def authenticate(self):
        loop = asyncio.get_event_loop()
        garth.configure(domain="garmin.com")

        if self.token_file.exists():
            try:
                logger.info(f"Attempting to resume session for {self.profile_name}...")
                with open(self.token_file, "r") as f:
                    saved_tokens = f.read().strip()
                
                self.client.garth.loads(saved_tokens)
                self._authenticated = True
                logger.info(f"Resumed session successfully for {self.email}")
                await self._fetch_user_profile_info()
                return
            except Exception as e:
                logger.warning(f"Failed to resume session for {self.profile_name}: {e}")

        try:
            def login_wrapper():
                return self.client.login()
            
            await loop.run_in_executor(None, login_wrapper)
            self._authenticated = True
            self.mfa_ticket_dict = None
            logger.info(f"Authenticated successfully as {self.email} (Fresh Login)")
            await self._fetch_user_profile_info()
            
            self.save_session()

        except AttributeError as e:
            if "'dict' object has no attribute 'expired'" in str(e):
                logger.info("Caught AttributeError indicating MFA challenge.")
                if hasattr(self.client.garth, 'oauth2_token') and isinstance(self.client.garth.oauth2_token, dict):
                    self.mfa_ticket_dict = self.client.garth.oauth2_token
                    raise MFARequiredException(message="MFA code is required.", mfa_data=self.mfa_ticket_dict)
                raise
            raise
        except garminconnect.GarminConnectAuthenticationError as e:
            if "MFA-required" in str(e) or "Authentication failed" in str(e):
                if hasattr(self.client.garth, 'oauth2_token') and isinstance(self.client.garth.oauth2_token, dict):
                    self.mfa_ticket_dict = self.client.garth.oauth2_token 
                    raise MFARequiredException(message="MFA code is required.", mfa_data=self.mfa_ticket_dict)
            raise
        except Exception as e:
            logger.error(f"Authentication error: {str(e)}")
            raise garminconnect.GarminConnectAuthenticationError(f"Authentication error: {str(e)}") from e

    async def _fetch_user_profile_info(self):
        loop = asyncio.get_event_loop()
        
        # FIX: Explicitly fetch and force-inject the Garmin display_name if missing.
        # This completely bypasses the garminconnect library bug and parses the raw JSON.
        if not getattr(self.client, "display_name", None):
            try:
                logger.info(f"[{self.profile_name}] Display name missing from session. Manually fetching from Garmin API...")
                sp = await loop.run_in_executor(None, self.client.connectapi, "/userprofile-service/socialProfile")
                if sp and isinstance(sp, dict) and sp.get("displayName"):
                    self.client.display_name = sp["displayName"]
                    logger.info(f"[{self.profile_name}] Successfully locked in display name: {self.client.display_name}")
            except Exception as e:
                logger.debug(f"[{self.profile_name}] Could not force-fetch display name: {e}")

        if self.manual_name:
            self.user_full_name = self.manual_name
        if self.manual_gender:
            self.user_gender = self.manual_gender

        if self.manual_dob:
            try:
                dob = datetime.strptime(self.manual_dob, "%Y-%m-%d").date()
                today = date.today()
                self.user_age = round((today - dob).days / 365.25, 1)
            except ValueError:
                logger.warning(f"Invalid format for USER_DOB: {self.manual_dob}. Use YYYY-MM-DD.")

        try:
            if not self.user_full_name:
                display_name = self.client.display_name
                if display_name:
                    social_profile = await loop.run_in_executor(
                        None, self.client.get_social_profile, display_name
                    )
                    if social_profile:
                        self.user_full_name = social_profile.get('fullName')
            
            if not self.user_age:
                user_settings = await loop.run_in_executor(None, self.client.get_user_settings)
                if user_settings and
                
