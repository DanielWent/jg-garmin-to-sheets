from datetime import date, datetime
from typing import Dict, Any, Optional, List
import asyncio
import logging
import garminconnect
from garth.sso import resume_login
import garth
from .exceptions import MFARequiredException
from .config import GarminMetrics
from statistics import mean

logger = logging.getLogger(__name__)

class GarminClient:
    def __init__(self, email: str, password: str):
        self.client = garminconnect.Garmin(email, password)
        self._authenticated = False
        self.mfa_ticket_dict = None
        self._auth_failed = False

    async def authenticate(self):
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
            
            # --- NEW: Specific fetcher for Blood Pressure ---
            async def get_bp():
                try:
                    return await asyncio.get_event_loop().run_in_executor(None, self.client.get_blood_pressure, target_date.isoformat())
                except Exception as e:
                    # BP call might fail if no data or permission, so we handle it gracefully
                    logger.debug(f"Could not fetch BP for {target_date}: {e}")
                    return None

            # 2. Fetch all concurrently
            results = await asyncio.gather(
                get_stats(), get_sleep(), get_activities(), get_user_summary(), 
                get_training_status(), get_hrv(), get_bp(),
                return_exceptions=True
            )

            # Unpack safely
            stats = results[0] if not isinstance(results[0], Exception) else None
            sleep_data = results[1] if not isinstance(results[1], Exception) else None
            activities = results[2] if not isinstance(results[2], Exception) else None
            summary = results[3] if not isinstance(results[3], Exception) else None
            training_status = results[4] if not isinstance(results[4], Exception) else None
            hrv_payload = results[5] if not isinstance(results[5], Exception) else None
            bp_payload = results[6] if not isinstance(results[6], Exception) else None

            # 3. Process Sleep Data (Includes Efficiency)
            sleep_score = None
            sleep_length = None
            sleep_need = None
            sleep_efficiency = None
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

                    # Sleep Efficiency Calculation
                    if sleep_time_seconds and sleep_time_seconds > 0:
                        awake_sec = sleep_dto.get('awakeSleepSeconds') or 0
                        sleep_efficiency = round(((sleep_time_seconds - awake_sec) / sleep_time_seconds) * 100)

            # 4. Process HRV
            overnight_hrv_value = None
            hrv_status_value = None
            if hrv_payload and 'hrvSummary' in hrv_payload:
                hrv_summary = hrv_payload['hrvSummary']
                overnight_hrv_value = hrv_summary.get('lastNightAvg')
                hrv_status_value = hrv_summary.get('status')

            # 5. Process Activities
            processed_activities = []
            if activities:
                for activity in activities:
                    atype = activity.get('activityType', {})
                    try:
                        act_id = activity.get('activityId')
                        act_name = activity.get('activityName')
                        act_start_local = activity.get('startTimeLocal')
                        
                        act_time_str = ""
                        if act_start_local:
                             act_time_str = act_start_local.split(' ')[1][:5] if ' ' in act_start_local else ""
                        
                        dist_km = (activity.get('distance') or 0) / 1000
                        dur_min = (activity.get('duration') or 0) / 60
                        
                        pace_str = ""
                        if dist_km > 0 and dur_min > 0:
                             pace_decimal = dur_min / dist_km
                             p_min = int(pace_decimal)
                             p_sec = int((pace_decimal - p_min) * 60)
                             pace_str = f"{p_min}:{p_sec:02d}"

                        avg_hr = activity.get('averageHR')
                        max_hr = activity.get('maxHR')
                        avg_cadence = activity.get('averageRunningCadenceInStepsPerMinute')
                        if not avg_cadence:
                            avg_cadence = activity.get('averageBikingCadenceInRevPerMinute') 

                        cal = activity.get('calories')
                        elev = activity.get('elevationGain')
                        aerobic_te = activity.get('aerobicTrainingEffect')
                        anaerobic_te = activity.get('anaerobicTrainingEffect')

                        processed_activities.append({
                            "Activity ID": act_id,
                            "Date": target_date.isoformat(),
                            "Time": act_time_str,
                            "Type": atype.get('typeKey', 'Unknown'),
                            "Name": act_name,
                            "Distance (km)": round(dist_km, 2) if dist_km else 0,
                            "Duration (min)": round(dur_min, 1) if dur_min else 0,
                            "Avg Pace (min/km)": pace_str,
                            "Avg HR": int(avg_hr) if avg_hr else "",
                            "Max HR": int(max_hr) if max_hr else "",
                            "Calories": int(cal) if cal else "",
                            "Avg Cadence (spm)": int(avg_cadence) if avg_cadence else "",
                            "Elevation Gain (m)": int(elev) if elev else "",
                            "Aerobic TE": aerobic_te,
                            "Anaerobic TE": anaerobic_te
                        })
                    except Exception as e_act:
                        logger.error(f"Error parsing activity detail: {e_act}")
                        continue

            # 6. Process General Stats (BMI / Weight)
            weight = None
            body_fat = None
            bmi = None
            
            if stats:
                if stats.get('weight'): weight = stats.get('weight') / 1000
                body_fat = stats.get('bodyFat')
                bmi = stats.get('bmi')

            # --- NEW: Process Blood Pressure ---
            bp_systolic = None
            bp_diastolic = None
            
            if bp_payload and 'userDailyBloodPressureDTOList' in bp_payload:
                readings = bp_payload['userDailyBloodPressureDTOList']
                if readings:
                    # Calculate average if there are multiple readings for the day
                    sys_values = [r['systolic'] for r in readings if r.get('systolic')]
                    dia_values = [r['diastolic'] for r in readings if r.get('diastolic')]
                    
                    if sys_values:
                        bp_systolic = int(round(mean(sys_values)))
                    if dia_values:
                        bp_diastolic = int(round(mean(dia_values)))

            # 7. Summary Stats
            active_cal = None
            resting_cal = None
            intensity_min = None
            resting_hr = None
            avg_stress = None
            steps = None
            floors = None
            rest_stress_dur = None
            low_stress_dur = None
            med_stress_dur = None
            high_stress_dur = None
            
            if summary:
                active_cal = summary.get('activeKilocalories')
                resting_cal = summary.get('bmrKilocalories')
                intensity_min = (summary.get('moderateIntensityMinutes', 0) or 0) + (2 * (summary.get('vigorousIntensityMinutes', 0) or 0))
                resting_hr = summary.get('restingHeartRate')
                avg_stress = summary.get('averageStressLevel')
                steps = summary.get('totalSteps')
                
                # Stress Durations
                rest_stress_dur = summary.get('restStressDuration')
                low_stress_dur = summary.get('lowStressDuration')
                med_stress_dur = summary.get('mediumStressDuration')
                high_stress_dur = summary.get('highStressDuration')

                raw_floors = summary.get('floorsAscended') or summary.get('floorsClimbed')
                if raw_floors is not None:
                    try:
                        floors = round(float(raw_floors))
                    except (ValueError, TypeError):
                        floors = raw_floors

            # 8. Training Status
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

            return GarminMetrics(
                date=target_date,
                sleep_score=sleep_score,
                sleep_need=sleep_need,
                sleep_efficiency=sleep_efficiency,
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
                bmi=bmi,
                body_fat=body_fat,
                blood_pressure_systolic=bp_systolic,
                blood_pressure_diastolic=bp_diastolic,
                resting_heart_rate=resting_hr,
                average_stress=avg_stress,
                rest_stress_duration=rest_stress_dur,
                low_stress_duration=low_stress_dur,
                medium_stress_duration=med_stress_dur,
                high_stress_duration=high_stress_dur,
                overnight_hrv=overnight_hrv_value,
                hrv_status=hrv_status_value,
                vo2max_running=vo2_run,
                vo2max_cycling=vo2_cycle,
                training_status=train_phrase,
                active_calories=active_cal,
                resting_calories=resting_cal,
                intensity_minutes=intensity_min,
                steps=steps,
                floors_climbed=floors,
                activities=processed_activities
            )

        except Exception as e:
            logger.error(f"Error fetching metrics for {target_date}: {str(e)}")
            return GarminMetrics(date=target_date)
