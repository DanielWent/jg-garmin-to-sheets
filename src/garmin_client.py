from datetime import date, datetime
from typing import Dict, Any, Optional, List
import asyncio
import logging
import garminconnect
from garth.sso import resume_login
import garth
from .exceptions import MFARequiredException
from .config import GarminMetrics
import traceback

logger = logging.getLogger(__name__)

class GarminClient:
    def __init__(self, email: str, password: str):
        self.client = garminconnect.Garmin(email, password)
        self._authenticated = False
        self.mfa_ticket_dict = None
        self._auth_failed = False

    async def authenticate(self):
        """Modified to handle non-async login method"""
        print("Authenticating with Garmin...")
        try:
            def login_wrapper():
                return self.client.login()
            
            await asyncio.get_event_loop().run_in_executor(None, login_wrapper)
            self._authenticated = True
            self.mfa_ticket_dict = None
            print("Authentication successful.")

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
            print(f"   [!] HRV Data missing: {e}")
            return None

    async def get_metrics(self, target_date: date) -> GarminMetrics:
        if not self._authenticated:
            if self._auth_failed:
                raise Exception("Authentication previously failed.")
            await self.authenticate()

        date_str = target_date.isoformat()
        print(f"\n--- Fetching Data for {date_str} (Sequential Mode) ---")

        # Define a synchronous helper to run inside the executor
        # This ensures we use one thread and do not trigger rate limits with parallel calls
        def fetch_all_sync():
            data = {}
            
            print("1. Fetching Daily Stats...")
            try: data['stats'] = self.client.get_stats_and_body(date_str)
            except Exception as e: print(f"   Error: {e}"); data['stats'] = None

            print("2. Fetching Sleep Data...")
            try: data['sleep'] = self.client.get_sleep_data(date_str)
            except Exception as e: print(f"   Error: {e}"); data['sleep'] = None

            print("3. Fetching Activity List...")
            try: data['activities'] = self.client.get_activities_by_date(date_str, date_str)
            except Exception as e: print(f"   Error: {e}"); data['activities'] = []

            print("4. Fetching User Summary...")
            try: data['summary'] = self.client.get_user_summary(date_str)
            except Exception as e: print(f"   Error: {e}"); data['summary'] = None

            print("5. Fetching Training Status...")
            try: data['training_status'] = self.client.get_training_status(date_str)
            except Exception as e: print(f"   Error: {e}"); data['training_status'] = None

            return data

        try:
            # Run the big sequential fetcher
            results = await asyncio.get_event_loop().run_in_executor(None, fetch_all_sync)
            
            # Fetch HRV separately (since it's already async compatible in this class)
            print("6. Fetching HRV...")
            hrv_payload = await self._fetch_hrv_data(date_str)

            # Unpack
            stats = results.get('stats')
            sleep_data = results.get('sleep')
            activity_summaries = results.get('activities')
            summary = results.get('summary')
            training_status = results.get('training_status')

            # --- PROCESS SLEEP ---
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

            # --- PROCESS HRV ---
            overnight_hrv_value = hrv_status_value = None
            if hrv_payload and 'hrvSummary' in hrv_payload:
                hrv_summary = hrv_payload['hrvSummary']
                overnight_hrv_value = hrv_summary.get('lastNightAvg')
                hrv_status_value = hrv_summary.get('status')

            # --- PROCESS ACTIVITIES (SEQUENTIAL DETAIL FETCH) ---
            running_count = running_distance = cycling_count = cycling_distance = 0
            strength_count = strength_duration = cardio_count = cardio_duration = 0
            tennis_count = tennis_duration = 0
            processed_activities = []

            if activity_summaries:
                print(f"   Found {len(activity_summaries)} activities. Fetching details one by one...")
                for idx, act in enumerate(activity_summaries):
                    act_id = act.get('activityId')
                    print(f"   -> Processing Activity {idx+1}/{len(activity_summaries)} (ID: {act_id})...")
                    
                    # FETCH DETAIL SEQUENTIALLY
                    try:
                        detailed_act = await asyncio.get_event_loop().run_in_executor(
                            None, self.client.get_activity_details, act_id
                        )
                    except Exception as e:
                        print(f"      [!] Failed to get details for {act_id}: {e}")
                        continue

                    # In detailed view, metrics are inside 'summaryDTO'
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
                        act_name = activity.get('activityName')
                        act_start_local = activity.get('startTimeLocal')
                        act_time_str = act_start_local.split(' ')[1][:5] if act_start_local and ' ' in act_start_local else ""
                        
                        dist_km = (activity.get('distance') or 0) / 1000
                        dur_min = (activity.get('duration') or 0) / 60
                        pace_str = ""
                        if dist_km > 0 and dur_min > 0:
                             pace_decimal = dur_min / dist_km
                             pace_str = f"{int(pace_decimal)}:{int((pace_decimal - int(pace_decimal)) * 60):02d}"

                        # HR Zones (Safe Logic)
                        hr_zones = activity.get('timeInHRZones', [])
                        z_m = []
                        for i in range(6):
                            val = hr_zones[i] if hr_zones and len(hr_zones) > i else 0
                            z_m.append(round((val or 0) / 60, 2))

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
                        print(f"      [!] Error parsing activity details: {e_act}")

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

            print("Data processing complete. Returning metrics.")
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
            print("CRITICAL FAILURE IN GET_METRICS")
            traceback.print_exc()
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
