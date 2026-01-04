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
            sleep_need = None
            sleep_start_time = None
            sleep_end_time = None
            sleep_deep = None
            sleep_light = None
            sleep_rem = None
            sleep_awake = None
            overnight_respiration = None
            overnight_pulse_ox = None

            if sleep_data:
                sleep_dto = sleep_data.get('dailySleepDTO', {})
                if sleep_dto:
                    sleep_score = sleep_dto.get('sleepScores', {}).get('overall', {}).get('value')
                    
                    sleep_need_obj = sleep_dto.get('sleepNeed')
                    if isinstance(sleep_need_obj, dict):
                        sleep_need = sleep_need_obj.get('actual')
                    else:
                        sleep_need = sleep_need_obj

                    overnight_respiration = sleep_dto.get('averageRespirationValue')
                    overnight_pulse_ox = sleep_dto.get('averageSpO2Value')

                    sleep_time_seconds = sleep_dto.get('sleepTimeSeconds')
                    if sleep_time_seconds:
                        sleep_length = sleep_time_seconds / 3600  # Hours
                    
                    start_ts_local = sleep_dto.get('sleepStartTimestampLocal')
                    end_ts_local = sleep_dto.get('sleepEndTimestampLocal')
                    
                    if start_ts_local:
                        sleep_start_time = datetime.fromtimestamp(start_ts_local/1000).strftime('%H:%M')
                    if end_ts_local:
                        sleep_end_time = datetime.fromtimestamp(end_ts_local/1000).strftime('%H:%M')
                    
                    sleep_deep = (sleep_dto.get('deepSleepSeconds') or 0) / 60
                    sleep_light = (sleep_dto.get('lightSleepSeconds') or 0) / 60
                    sleep_rem = (sleep_dto.get('remSleepSeconds') or 0) / 60
                    sleep_awake = (sleep_dto.get('awakeSleepSeconds') or 0) / 60

            # 4. Process Lactate Threshold
            lactate_pace = None
            lactate_hr = None
            lt_speed = None
            lt_hr_raw = None

            def parse_lt_obj(obj):
                if not obj: return None, None
                s = obj.get('value') or obj.get('speed')
                h = obj.get('hrValue') or obj.get('bpm') or obj.get('hr')
                return s, h

            if training_status:
                lt_obj = training_status.get('mostRecentLactateThreshold', {})
                s, h = parse_lt_obj(lt_obj)
                if s: lt_speed = s
                if h: lt_hr_raw = h
            
            if (not lt_speed or not lt_hr_raw) and summary:
                lt_obj = summary.get('latestLactateThreshold', {})
                s, h = parse_lt_obj(lt_obj)
                if not lt_speed and s: lt_speed = s
                if not lt_hr_raw and h: lt_hr_raw = h

            if lt_hr_raw:
                lactate_hr = lt_hr_raw

            if lt_speed and lt_speed > 0:
                seconds_per_km = 1000 / lt_speed
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

            # 7. Process General Stats & HR Zones
            weight = None
            body_fat = None
            if stats:
                if stats.get('weight'): weight = stats.get('weight') / 1000
                body_fat = stats.get('bodyFat')

            active_cal = None
            resting_cal = None
            intensity_min = None
            resting_hr = None
            avg_stress = None
            steps = None
            floors = None
            
            # Init Zones
            z0 = z1 = z2 = z3 = z4 = z5 = None

            if summary:
                active_cal = summary.get('activeKilocalories')
                resting_cal = summary.get('bmrKilocalories')
                intensity_min = (summary.get('moderateIntensityMinutes', 0) or 0) + (2 * (summary.get('vigorousIntensityMinutes', 0) or 0))
                resting_hr = summary.get('restingHeartRate')
                avg_stress = summary.get('averageStressLevel')
                steps = summary.get('totalSteps')
                
                # Floors
                raw_floors = summary.get('floorsAscended') or summary.get('floorsClimbed')
                if raw_floors is not None:
                    try:
                        floors = round(float(raw_floors))
                    except (ValueError, TypeError):
                        floors = raw_floors
                
                # --- NEW: HR Zones ---
                # 'timeInHeartRateZones' is usually a dict {0: seconds, 1: seconds...}
                zones_obj = summary.get('timeInHeartRateZones')
                if zones_obj and isinstance(zones_obj, dict):
                    # Helper to get minutes
                    def get_z_min(idx):
                        val = zones_obj.get(str(idx)) or zones_obj.get(idx)
                        return (val / 60) if val else 0
                    
                    z0 = get_z_min(0)
                    z1 = get_z_min(1)
                    z2 = get_z_min(2)
                    z3 = get_z_min(3)
                    z4 = get_z_min(4)
                    z5 = get_z_min(5)


            # 8. Training Status / VO2 Max
            vo2_run = None
            vo2_cycle = None
            train_phrase = None
            
            if training_status:
                mr_vo2 = training_status.get('mostRecentVO2Max', {})
                if mr_vo2.get('generic'): vo2_run = mr_vo2['generic'].get('vo2MaxValue')
                if mr_vo2.get('cycling'): vo2_cycle = mr_vo2['cycling'].get('vo2MaxValue')
                
                ts_data = training_status.get('mostRecentTrainingStatus', {}).get('latestTrainingStatusData', {})
                if ts_data:
                    for dev_data in ts_data.values():
                        train_phrase = dev_data.get('trainingStatusFeedbackPhrase')
                        break

            # Return populated object
            return GarminMetrics(
                date=target_date,
                sleep_score=sleep_score,
                sleep_need=sleep_need,             
                sleep_length=sleep_length,
                sleep_start_time=sleep_start_time, 
                sleep_end_time=sleep_end_time,     
                sleep_deep=sleep_deep,             
                sleep_light=sleep_light,           
                sleep_rem=sleep_rem,               
                sleep_awake=sleep_awake,
                overnight_respiration=overnight_respiration, 
                overnight_pulse_ox=overnight_pulse_ox,       
                weight=weight,
                body_fat=body_fat,
                resting_heart_rate=resting_hr,
                average_stress=avg_stress,
                overnight_hrv=overnight_hrv_value,
                hrv_status=hrv_status_value,
                hr_zone_0=z0, # NEW
                hr_zone_1=z1, # NEW
                hr_zone_2=z2, # NEW
                hr_zone_3=z3, # NEW
                hr_zone_4=z4, # NEW
                hr_zone_5=z5, # NEW
                vo2max_running=vo2_run,
                vo2max_cycling=vo2_cycle,
                training_status=train_phrase,
                lactate_threshold_pace=lactate_pace, 
                lactate_threshold_hr=lactate_hr,     
                active_calories=active_cal,
