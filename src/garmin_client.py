from datetime import date, datetime
from typing import Dict, Any, Optional, List
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
            # 1. Define async fetchers for daily summaries
            async def get_stats():
                return await asyncio.get_event_loop().run_in_executor(None, self.client.get_stats_and_body, target_date.isoformat())
            async def get_sleep():
                return await asyncio.get_event_loop().run_in_executor(None, self.client.get_sleep_data, target_date.isoformat())
            async def get_activity_list():
                return await asyncio.get_event_loop().run_in_executor(None, self.client.get_activities_by_date, target_date.isoformat(), target_date.isoformat())
            async def get_user_summary():
                return await asyncio.get_event_loop().run_in_executor(None, self.client.get_user_summary, target_date.isoformat())
            async def get_training_status():
                return await asyncio.get_event_loop().run_in_executor(None, self.client.get_training_status, target_date.isoformat())
            async def get_hrv():
                return await self._fetch_hrv_data(target_date.isoformat())

            # 2. Fetch all daily summaries concurrently
            stats, sleep_data, activity_summaries, summary, training_status, hrv_payload = await asyncio.gather(
                get_stats(), get_sleep(), get_activity_list(), get_user_summary(), get_training_status(), get_hrv()
            )

            # 3. Process Sleep Data
            sleep_score = sleep_length = sleep_need = sleep_start_time = sleep_end_time = None
            sleep_deep = sleep_light = sleep_rem = sleep_awake = None
            overnight_respiration = overnight_pulse_ox = None

            if sleep_data:
                sleep_dto = sleep_data.get('dailySleepDTO', {})
                if sleep_dto:
                    sleep_score = sleep_dto.get('sleepScores', {}).get('overall', {}).get('value')
                    sleep_need_obj = sleep_dto.get('sleepNeed')
                    sleep_need = sleep_need_obj.get('actual') if isinstance(sleep_need_obj, dict) else sleep_need_obj
                    overnight_respiration = sleep_dto.get('averageRespirationValue')
                    overnight_pulse_ox = sleep_dto.get('averageSpO2Value')
                    sleep_time_seconds = sleep_dto.get('sleepTimeSeconds')
                    if sleep_time_seconds:
                        sleep_length = round(sleep_time_seconds / 60)
                    
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

            # 4. Process HRV
            overnight_hrv_value = hrv_status_value = None
            if hrv_payload and 'hrvSummary' in hrv_payload:
                hrv_summary = hrv_payload['hrvSummary']
                overnight_hrv_value = hrv_summary.get('lastNightAvg')
                hrv_status_value = hrv_summary.get('status')

            # 5. Process Activities (NOW WITH DOUBLE FETCH FOR DETAILS)
            running_count = running_distance = cycling_count = cycling_distance = 0
            strength_count = strength_duration = cardio_count = cardio_duration = 0
            tennis_count = tennis_duration = 0
            processed_activities = []

            # --- CRITICAL FIX START: Fetch full details for HR Zones ---
            detailed_activities = []
            if activity_summaries:
                try:
                    # Create a list of tasks to fetch details for each activity ID found
                    detail_tasks = [
                        asyncio.get_event_loop().run_in_executor(
                            None, self.client.get_activity_details, act.get('activityId')
                        )
                        for act in activity_summaries
                    ]
                    # Run them all at once
                    detailed_activities = await asyncio.gather(*detail_tasks)
                except Exception as e:
                    logger.error(f"Failed to fetch detailed activity data: {e}")
            # --- CRITICAL FIX END ---

            if detailed_activities:
                for detailed_act in detailed_activities:
                    # In the detailed view, the main stats are nested inside 'summaryDTO'
                    activity = detailed_act.get('summaryDTO', {})
                    if not activity: continue

                    atype = activity.get('activityType', {})
                    type_key = atype.get('typeKey', '').lower()
                    parent_id = atype.get('parentTypeId')
                    
                    # Totals Aggregation
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
                    
                    # Detail Processing
                    try:
                        act_id = activity.get('activityId')
                        act_name = activity.get('activityName')
                        act_start_local = activity.get('startTimeLocal')
                        act_time_str = act_start_local.split(' ')[1][:5] if act_start_local and ' ' in act_start_local else ""
                        
                        dist_km = (activity.get('distance') or 0) / 1000
                        dur_min = (activity.get('duration') or 0) / 60
                        pace_str = ""
                        if dist_km > 0 and dur_min > 0:
                             pace_decimal = dur_min / dist_km
                             pace_str = f"{int(pace_decimal)}:{int((pace_decimal - int(pace_decimal)) * 60):02d}"

                        # HR Zones (Now available because we fetched details)
                        hr_zones = activity.get('timeInHRZones', [])
                        # Create a safe list of minutes, defaulting to 0 if index missing
                        z_m = [round(hr_zones[i] / 60, 2) if len(hr_zones) > i else 0 for i in range(6)]

                        processed_activities.append({
                            "Activity ID": act_id,
                            "Date": target_date.isoformat(),
                            "Time": act_time_str,
                            "Type": atype.get('typeKey', 'Unknown'),
                            "Name": act_name,
                            "Distance (km)": round(dist_km, 2),
                            "Duration (min)": round(dur_min, 1),
                            "Avg Pace (min/km)": pace_str,
                            "Avg HR": int(activity.get('averageHR') or 0),
                            "Max HR": int(activity.get('maxHR') or 0),
                            "Calories": int(activity.get('calories') or 0),
                            "Avg Cadence (spm)": int(activity.get('averageRunningCadenceInStepsPerMinute') or activity.get('averageBikingCadenceInRevPerMinute') or 0),
                            "Elevation Gain (m)": int(activity.get('elevationGain') or 0),
                            "Aerobic TE": activity.get('aerobicTrainingEffect'),
                            "Anaerobic TE": activity.get('anaerobicTrainingEffect'),
                            "Z1 Time (min)": z_m[1],
                            "Z2 Time (min)": z_m[2],
                            "Z3 Time (min)": z_m[3],
                            "Z4 Time (min)": z_m[4],
                            "Z5 Time (min)": z_m[5]
                        })
                    except Exception as e_act:
                        logger.error(f"Error parsing activity detail: {e_act}")

            # 6. Process General Stats
            weight = body_fat = None
            if stats:
                weight = stats.get('weight', 0) / 1000 if stats.get('weight') else None
                body_fat = stats.get('bodyFat')

            active_cal = resting_cal = intensity_min = resting_hr = avg_stress = steps = floors = None
            if summary:
                active_cal = summary.get('activeKilocalories')
                resting_cal = summary.get('bmrKilocalories')
                intensity_min = (summary.get('moderateIntensityMinutes', 0) or 0) + (2 * (summary.get('vigorousIntensityMinutes', 0) or 0))
                resting_hr = summary.get('restingHeartRate')
                avg_stress = summary.get('averageStressLevel')
                steps = summary.get('totalSteps')
                raw_floors = summary.get('floorsAscended') or summary.get('floorsClimbed')
                floors = round(float(raw_floors)) if raw_floors is not None else None

            # 7. Training Status
            vo2_run = vo2_cycle = train_phrase = None
            if training_status:
                mr_vo2 = training_status.get('mostRecentVO2Max', {})
                vo2_run = mr_vo2.get('generic', {}).get('vo2MaxValue')
                vo2_cycle = mr_vo2.get('cycling', {}).get('vo2MaxValue')
                ts_data = training_status.get('mostRecentTrainingStatus', {}).get('latestTrainingStatusData', {})
                for dev_data in ts_data.values():
                    train_phrase = dev_data.get('trainingStatusFeedbackPhrase')
                    break

            return GarminMetrics(
                date=target_date, sleep_score=sleep_score, sleep_need=sleep_need, sleep_length=sleep_length,
                sleep_start_time=sleep_start_time, sleep_end_time=sleep_end_time, sleep_deep=sleep_deep,
                sleep_light=sleep_light, sleep_rem=sleep_rem, sleep_awake=sleep_awake,
                overnight_respiration=overnight_respiration, overnight_pulse_ox=overnight_pulse_ox,
                weight=weight, body_fat=body_fat, resting_heart_rate=resting_hr, average_stress=avg_stress,
                overnight_hrv=overnight_hrv_value, hrv_status=hrv_status_value, vo2max_running=vo2_run,
                vo2max_cycling=vo2_cycle, training_status=train_phrase, active_calories=active_cal,
                resting_calories=resting_cal, intensity_minutes=intensity_min, steps=steps, floors_climbed=floors,
                all_activity_count=len(activity_summaries) if activity_summaries else 0,
                running_activity_count=running_count, running_distance=running_distance,
                cycling_activity_count=cycling_count, cycling_distance=cycling_distance,
                strength_activity_count=strength_count, strength_duration=strength_duration,
                cardio_activity_count=cardio_count, cardio_duration=cardio_duration,
                tennis_activity_count=tennis_count, tennis_activity_duration=tennis_duration,
                activities=processed_activities
            )

        except Exception as e:
            logger.error(f"Error fetching metrics for {target_date}: {str(e)}")
            return GarminMetrics(date=target_date)

    async def submit_mfa_code(self, mfa_code: str):
        if not self.mfa_ticket_dict: raise Exception("MFA ticket not available.")
        try:
            loop = asyncio.get_event_loop()
            oauth1, oauth2 = await loop.run_in_executor(None, lambda: resume_login(self.mfa_ticket_dict, mfa_code))
            self.client.garth.oauth1_token, self.client.garth.oauth2_token = oauth1, oauth2
            self._authenticated, self.mfa_ticket_dict = True, None
            return True
        except Exception as e:
            self._authenticated, self._auth_failed = False, True
            raise Exception(f"MFA submission failed: {str(e)}")
