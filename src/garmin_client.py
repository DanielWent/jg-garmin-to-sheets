from datetime import date, datetime
from typing import Dict, Any, Optional
import asyncio
import logging
import garminconnect
from garth.sso import resume_login
import garth
from .exceptions import MFARequiredException
from .config import GarminMetrics

logger = logging.getLogger(__name__)

class GarminClient:
    def __init__(self, email: str, password: str):
        self.client = garminconnect.Garmin(email, password)
        self._authenticated = False
        self.mfa_ticket_dict = None
        self._auth_failed = False

    async def authenticate(self):
        """Modified to handle non-async login method"""
        try:
            def login_wrapper():
                return self.client.login()
            
            await asyncio.get_event_loop().run_in_executor(None, login_wrapper)
            self._authenticated = True
            self.mfa_ticket_dict = None

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

    async def _fetch_hrv_data(self, target_date_iso: str) -> Optional[Dict[str, Any]]:
        try:
            return await asyncio.get_event_loop().run_in_executor(
                None, self.client.get_hrv_data, target_date_iso
            )
        except Exception as e:
            logger.error(f"Error fetching HRV data: {str(e)}")
            return None

    async def get_metrics(self, target_date: date) -> GarminMetrics:
        if not self._authenticated:
            if self._auth_failed:
                raise Exception("Authentication previously failed.")
            await self.authenticate()

        try:
            # 1. Define async fetchers
            async def get_stats():
                return await asyncio.get_event_loop().run_in_executor(None, self.client.get_stats_and_body, target_date.isoformat())
            async def get_sleep():
                return await asyncio.get_event_loop().run_in_executor(None, self.client.get_sleep_data, target_date.isoformat())
            async def get_activities():
                return await asyncio.get_event_loop().run_in_executor(None, self.client.get_activities_by_date, target_date.isoformat(), target_date.isoformat())
            async def get_user_summary():
                return await asyncio.get_event_loop().run_in_executor(None, self.client.get_user_summary, target_date.isoformat())
            async def get_training_status():
                return await asyncio.get_event_loop().run_in_executor(None, self.client.get_training_status, target_date.isoformat())
            async def get_hrv():
                return await self._fetch_hrv_data(target_date.isoformat())

            # 2. Fetch all concurrently
            stats, sleep_data, activities, summary, training_status, hrv_payload = await asyncio.gather(
                get_stats(), get_sleep(), get_activities(), get_user_summary(), get_training_status(), get_hrv()
            )

            # 3. Process Sleep Data
            sleep_score = None
            sleep_length = None
            sleep_start_time = None
            sleep_end_time = None
            sleep_deep = None
            sleep_light = None
            sleep_rem = None
            sleep_awake = None

            if sleep_data:
                sleep_dto = sleep_data.get('dailySleepDTO', {})
                if sleep_dto:
                    sleep_score = sleep_dto.get('sleepScores', {}).get('overall', {}).get('value')
                    
                    # Times
                    sleep_time_seconds = sleep_dto.get('sleepTimeSeconds')
                    if sleep_time_seconds:
                        sleep_length = sleep_time_seconds / 3600  # Hours
                    
                    # Start/End Times (Format HH:MM)
                    start_ts = sleep_dto.get('sleepStartTimestampGMT') # Using GMT usually works best with Garmin's offset logic, or check for local
                    # Actually, Garmin provides 'sleepStartTimestampLocal' which is safer for display
                    start_ts_local = sleep_dto.get('sleepStartTimestampLocal')
                    end_ts_local = sleep_dto.get('sleepEndTimestampLocal')
                    
                    if start_ts_local:
                        sleep_start_time = datetime.fromtimestamp(start_ts_local/1000).strftime('%H:%M')
                    if end_ts_local:
                        sleep_end_time = datetime.fromtimestamp(end_ts_local/1000).strftime('%H:%M')
                    
                    # Sleep Stages (Seconds to Minutes)
                    sleep_deep = (sleep_dto.get('deepSleepSeconds') or 0) / 60
                    sleep_light = (sleep_dto.get('lightSleepSeconds') or 0) / 60
                    sleep_rem = (sleep_dto.get('remSleepSeconds') or 0) / 60
                    sleep_awake = (sleep_dto.get('awakeSleepSeconds') or 0) / 60

            # 4. Process Lactate Threshold
            lactate_pace = None
            lactate_hr = None
            
            if training_status:
                lt_data = training_status.get('mostRecentLactateThreshold', {})
                if lt_data:
                    # Heart Rate
                    lactate_hr = lt_data.get('hrValue')
                    
                    # Pace (Speed is m/s. Need min/km)
                    speed_mps = lt_data.get('value')
                    if speed_mps and speed_mps > 0:
                        seconds_per_km = 1000 / speed_mps
                        minutes = int(seconds_per_km // 60)
                        seconds = int(seconds_per_km % 60)
                        lactate_pace = f"{minutes}:{seconds:02d}"

            # 5. Process HRV
            overnight_hrv_value = None
            hrv_status_value = None
            if hrv_payload and 'hrvSummary' in hrv_payload:
                hrv_summary = hrv_payload['hrvSummary']
                overnight_hrv_value = hrv_summary.get('lastNightAvg')
                hrv_status_value = hrv_summary.get('status')

            # 6. Process Activities
            running_count = 0
            running_distance = 0
            cycling_count = 0
            cycling_distance = 0
            strength_count = 0
            strength_duration = 0
            cardio_count = 0
            cardio_duration = 0
            tennis_count = 0
            tennis_duration = 0

            if activities:
                for activity in activities:
                    atype = activity.get('activityType', {})
                    type_key = atype.get('typeKey', '').lower()
                    parent_id = atype.get('parentTypeId')
                    
                    # Activity Logic
                    if 'run' in type_key or parent_id == 1:
                        running_count += 1
                        running_distance += activity.get('distance', 0) / 1000
                    elif 'cycling' in type_key or parent_id == 2:
                        cycling_count += 1
                        cycling_distance += activity.get('distance', 0) / 1000
                    elif 'strength' in type_key:
                        strength_count += 1
                        strength_duration += activity.get('duration', 0) / 60
                    elif 'cardio' in type_key:
                        cardio_count += 1
                        cardio_duration += activity.get('duration', 0) / 60
                    elif 'tennis' in type_key:
                        tennis_count += 1
                        tennis_duration += activity.get('duration', 0) / 60

            # 7. Process General Stats
            weight = None
            body_fat = None
            bp_sys = None
            bp_dia = None
            if stats:
                if stats.get('weight'): weight = stats.get('weight') / 1000
                body_fat = stats.get('bodyFat')
                bp_sys = stats.get('systolic')
                bp_dia = stats.get('diastolic')

            active_cal = None
            resting_cal = None
            intensity_min = None
            resting_hr = None
            avg_stress = None
            steps = None
            
            if summary:
                active_cal = summary.get('activeKilocalories')
                resting_cal = summary.get('bmrKilocalories')
                intensity_min = (summary.get('moderateIntensityMinutes', 0) or 0) + (2 * (summary.get('vigorousIntensityMinutes', 0) or 0))
                resting_hr = summary.get('restingHeartRate')
                avg_stress = summary.get('averageStressLevel')
                steps = summary.get('totalSteps')

            # 8. Training Status / VO2 Max
            vo2_run = None
            vo2_cycle = None
            train_phrase = None
            
            if training_status:
                mr_vo2 = training_status.get('mostRecentVO2Max', {})
                if mr_vo2.get('generic'): vo2_run = mr_vo2['generic'].get('vo2MaxValue')
                if mr_vo2.get('cycling'): vo2_cycle = mr_vo2['cycling'].get('vo2MaxValue')
                
                # Phrase logic
                ts_data = training_status.get('mostRecentTrainingStatus', {}).get('latestTrainingStatusData', {})
                if ts_data:
                    # Just grab the first available device's status
                    for dev_data in ts_data.values():
                        train_phrase = dev_data.get('trainingStatusFeedbackPhrase')
                        break

            # Return populated object
            return GarminMetrics(
                date=target_date,
                sleep_score=sleep_score,
                sleep_length=sleep_length,
                sleep_start_time=sleep_start_time, # NEW
                sleep_end_time=sleep_end_time,     # NEW
                sleep_deep=sleep_deep,             # NEW
                sleep_light=sleep_light,           # NEW
                sleep_rem=sleep_rem,               # NEW
                sleep_awake=sleep_awake,           # NEW
                weight=weight,
                body_fat=body_fat,
                resting_heart_rate=resting_hr,
                average_stress=avg_stress,
                overnight_hrv=overnight_hrv_value,
                hrv_status=hrv_status_value,
                vo2max_running=vo2_run,
                vo2max_cycling=vo2_cycle,
                training_status=train_phrase,
                lactate_threshold_pace=lactate_pace, # NEW
                lactate_threshold_hr=lactate_hr,     # NEW
                active_calories=active_cal,
                resting_calories=resting_cal,
                intensity_minutes=intensity_min,
                steps=steps,
                all_activity_count=len(activities) if activities else 0,
                running_activity_count=running_count,
                running_distance=running_distance,
                cycling_activity_count=cycling_count,
                cycling_distance=cycling_distance,
                strength_activity_count=strength_count,
                strength_duration=strength_duration,
                cardio_activity_count=cardio_count,
                cardio_duration=cardio_duration,
                tennis_activity_count=tennis_count,
                tennis_activity_duration=tennis_duration
            )

        except Exception as e:
            logger.error(f"Error fetching metrics for {target_date}: {str(e)}")
            # Return basic object with date to prevent crash
            return GarminMetrics(date=target_date)

    async def submit_mfa_code(self, mfa_code: str):
        if not self.mfa_ticket_dict:
            raise Exception("MFA ticket not available.")
        try:
            loop = asyncio.get_event_loop()
            resume_login_result = await loop.run_in_executor(
                None, lambda: resume_login(self.mfa_ticket_dict, mfa_code)
            )
            
            oauth1, oauth2 = resume_login_result
            self.client.garth.oauth1_token = oauth1
            self.client.garth.oauth2_token = oauth2
            
            self._authenticated = True
            self.mfa_ticket_dict = None
            return True
        except Exception as e:
            self._authenticated = False
            self._auth_failed = True
            raise Exception(f"MFA submission failed: {str(e)}")
