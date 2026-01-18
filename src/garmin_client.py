from datetime import date, datetime, timedelta
from typing import Dict, Any, Optional, List
import asyncio
import logging
import garminconnect
from garth.sso import resume_login
import garth
from .exceptions import MFARequiredException
from .config import GarminMetrics
from statistics import mean
from functools import partial

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

    def _find_training_load(self, data: Any) -> Optional[int]:
        """Recursively search for sevenDayLoad or acuteLoad in the JSON structure."""
        if not data:
            return None
        
        # Use a stack for iterative depth-first search to avoid recursion limits
        stack = [data]
        while stack:
            current = stack.pop()
            
            if isinstance(current, dict):
                # Check for the keys we want
                if 'sevenDayLoad' in current and current['sevenDayLoad'] is not None:
                    return int(round(current['sevenDayLoad']))
                if 'acuteLoad' in current and current['acuteLoad'] is not None:
                    return int(round(current['acuteLoad']))
                
                # Push values to stack to continue searching
                for value in current.values():
                    if isinstance(value, (dict, list)):
                        stack.append(value)
            
            elif isinstance(current, list):
                for item in current:
                    if isinstance(item, (dict, list)):
                        stack.append(item)
                        
        return None

    async def get_metrics(self, target_date: date) -> GarminMetrics:
        if not self._authenticated:
            if self._auth_failed:
                raise Exception("Authentication previously failed.")
            await self.authenticate()

        # --- HELPER: Parallel Fetch Wrapper ---
        async def safe_fetch(name, coro):
            try:
                # No artificial sleep needed for parallel execution
                return await coro
            except Exception as e:
                logger.warning(f"Failed to fetch {name} for {target_date}: {e}")
                return None

        try:
            target_iso = target_date.isoformat()
            loop = asyncio.get_event_loop()

            # ---------------------------------------------------------
            # 1. DEFINE TASKS (Prepare for Parallel Execution)
            # ---------------------------------------------------------
            
            # Use partial for endpoints requiring arguments to run_in_executor
            
            # Lactate Range Helpers
            task_lactate_hr_url = f"biometric-service/stats/lactateThresholdHeartRate/range/{target_iso}/{target_iso}"
            task_lactate_speed_url = f"biometric-service/stats/lactateThresholdSpeed/range/{target_iso}/{target_iso}"
            lactate_params = {'aggregationStrategy': 'LATEST', 'sport': 'RUNNING'}

            # Define all coroutines
            c_summary = safe_fetch("User Summary", loop.run_in_executor(None, self.client.get_user_summary, target_iso))
            c_stats = safe_fetch("Stats", loop.run_in_executor(None, self.client.get_stats_and_body, target_iso))
            c_sleep = safe_fetch("Sleep", loop.run_in_executor(None, self.client.get_sleep_data, target_iso))
            c_training = safe_fetch("Training Status", loop.run_in_executor(None, self.client.get_training_status, target_iso))
            c_hrv = self._fetch_hrv_data(target_iso)
            c_bp = safe_fetch("Blood Pressure", loop.run_in_executor(None, self.client.get_blood_pressure, target_iso))
            c_activities = safe_fetch("Activities", loop.run_in_executor(None, self.client.get_activities_by_date, target_iso, target_iso))
            
            c_lactate_direct = safe_fetch("Lactate Direct", loop.run_in_executor(None, self.client.connectapi, "biometric-service/biometric/latestLactateThreshold"))
            
            c_lactate_range_hr = safe_fetch("Lactate Range HR", loop.run_in_executor(
                None, partial(self.client.connectapi, task_lactate_hr_url, params=lactate_params)
            ))
            
            c_lactate_range_speed = safe_fetch("Lactate Range Speed", loop.run_in_executor(
                None, partial(self.client.connectapi, task_lactate_speed_url, params=lactate_params)
            ))

            # ---------------------------------------------------------
            # 2. EXECUTE PARALLEL FETCH
            # ---------------------------------------------------------
            
            results = await asyncio.gather(
                c_summary, c_stats, c_sleep, c_training, c_hrv, c_bp, 
                c_activities, c_lactate_direct, c_lactate_range_hr, c_lactate_range_speed
            )

            # Unpack results
            (summary, stats, sleep_data, training_status, hrv_payload, bp_payload, 
             activities, lactate_data, lactate_range_hr, lactate_range_speed) = results

            # ---------------------------------------------------------
            # 3. CONDITIONAL FETCH (Fallback)
            # ---------------------------------------------------------
            
            # Check if steps are missing from summary; if so, trigger fallback
            steps = None
            if summary:
                steps = summary.get('totalSteps')
            
            if steps is None:
                try:
                    daily_steps_data = await safe_fetch("Fallback Steps", loop.run_in_executor(None, self.client.get_daily_steps, target_iso, target_iso))
                    if daily_steps_data and isinstance(daily_steps_data, list) and len(daily_steps_data) > 0:
                        steps = daily_steps_data[0].get('totalSteps')
                        logger.info(f"Retrieved steps ({steps}) via fallback method.")
                except Exception as fb_err:
                    logger.debug(f"Fallback step fetch failed: {fb_err}")

            # ---------------------------------------------------------
            # 4. PARSE DATA
            # ---------------------------------------------------------
            
            # --- Sleep ---
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

                    if sleep_time_seconds and sleep_time_seconds > 0:
                        awake_sec = sleep_dto.get('awakeSleepSeconds') or 0
                        sleep_efficiency = round(((sleep_time_seconds - awake_sec) / sleep_time_seconds) * 100)

            # --- HRV ---
            overnight_hrv_value = None
            hrv_status_value = None
            if hrv_payload and 'hrvSummary' in hrv_payload:
                hrv_summary = hrv_payload['hrvSummary']
                overnight_hrv_value = hrv_summary.get('lastNightAvg')
                hrv_status_value = hrv_summary.get('status')

            # --- Activities ---
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

            # --- Stats (Weight/Body) ---
            weight = None
            body_fat = None
            bmi = None
            if stats:
                if stats.get('weight'): weight = stats.get('weight') / 1000
                body_fat = stats.get('bodyFat')
                bmi = stats.get('bmi')

            # --- Blood Pressure ---
            bp_systolic = None
            bp_diastolic = None
            if bp_payload:
                readings = []
                if isinstance(bp_payload, dict) and 'measurementSummaries' in bp_payload:
                    summaries = bp_payload.get('measurementSummaries', [])
                    if isinstance(summaries, list):
                        for summary_item in summaries:
                            if isinstance(summary_item, dict) and 'measurements' in summary_item:
                                batch = summary_item['measurements']
                                if isinstance(batch, list):
                                    readings.extend(batch)
                elif isinstance(bp_payload, list):
                    readings = bp_payload
                elif isinstance(bp_payload, dict) and 'userDailyBloodPressureDTOList' in bp_payload:
                    readings = bp_payload['userDailyBloodPressureDTOList']

                if readings:
                    try:
                        sys_values = [r['systolic'] for r in readings if isinstance(r, dict) and r.get('systolic')]
                        dia_values = [r['diastolic'] for r in readings if isinstance(r, dict) and r.get('diastolic')]
                        if sys_values: bp_systolic = int(round(mean(sys_values)))
                        if dia_values: bp_diastolic = int(round(mean(dia_values)))
                    except Exception as e:
                        logger.error(f"Error calculating BP average: {e}")

            # --- Summary Stats (Rest of Logic) ---
            active_cal = None
            resting_cal = None
            intensity_min = None
            resting_hr = None
            avg_stress = None
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
                # steps already handled above
                
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

            # --- Training Status & Lactate Threshold ---
            vo2_run = None
            vo2_cycle = None
            train_phrase = None
            lactate_bpm = None
            lactate_pace = None
            seven_day_load = None   # <--- NEW: Initialize variable

            # 1. Try Method A (Direct Latest)
            if lactate_data:
                if 'heartRate' in lactate_data:
                    lactate_bpm = lactate_data['heartRate']
                if 'speed' in lactate_data:
                    speed_ms = lactate_data['speed']
                    if speed_ms and speed_ms > 0:
                        sec_per_km = 1000 / speed_ms
                        p_min = int(sec_per_km / 60)
                        p_sec = int(sec_per_km % 60)
                        lactate_pace = f"{p_min}:{p_sec:02d}"
            
            # 2. Try Method B (Range Query) - If Method A failed
            # B1. Heart Rate
            if not lactate_bpm and lactate_range_hr and isinstance(lactate_range_hr, list):
                try:
                    last_entry = lactate_range_hr[-1] 
                    if isinstance(last_entry, dict):
                         if 'value' in last_entry:
                             lactate_bpm = int(last_entry['value'])
                except Exception as e:
                    logger.debug(f"Parsing lactate HR range failed: {e}")

            # B2. Pace (Speed)
            if not lactate_pace and lactate_range_speed and isinstance(lactate_range_speed, list):
                try:
                    last_entry = lactate_range_speed[-1]
                    if isinstance(last_entry, dict) and 'value' in last_entry:
                        speed_ms = last_entry['value']
                        
                        # --- 10x CORRECTION LOGIC ---
                        if speed_ms and speed_ms > 0:
                            if speed_ms < 1.0: 
                                speed_ms *= 10  # Correct decameters/s to m/s if needed
                            
                            sec_per_km = 1000 / speed_ms
                            p_min = int(sec_per_km / 60)
                            p_sec = int(sec_per_km % 60)
                            lactate_pace = f"{p_min}:{p_sec:02d}"
                except Exception as e:
                     logger.debug(f"Parsing lactate Speed range failed: {e}")

            # 3. Method C: Extract from Training Status (Robust Recursive Search)
            if training_status:
                # Use the helper to find load anywhere in the structure
                seven_day_load = self._find_training_load(training_status)

            # --- NEW FALLBACK ---
            # If still None, try finding it in the User Summary (common backup location)
            if seven_day_load is None and summary:
                seven_day_load = self._find_training_load(summary)
            # --------------------

                mr_vo2 = training_status.get('mostRecentVO2Max', {})
                if mr_vo2.get('generic'): vo2_run = mr_vo2['generic'].get('vo2MaxValue')
                if mr_vo2.get('cycling'): vo2_cycle = mr_vo2['cycling'].get('vo2MaxValue')
                
                ts_data = training_status.get('mostRecentTrainingStatus', {}).get('latestTrainingStatusData', {})
                if ts_data:
                    for dev_data in ts_data.values():
                        train_phrase = dev_data.get('trainingStatusFeedbackPhrase')
                        break
                
                if not lactate_bpm:
                    mr_ts = training_status.get('mostRecentTrainingStatus', {})
                    if mr_ts and 'lactateThresholdHeartRate' in mr_ts:
                        lactate_bpm = mr_ts['lactateThresholdHeartRate']

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
                seven_day_load=seven_day_load,        # <--- NEW: Pass to Constructor
                lactate_threshold_bpm=lactate_bpm,
                lactate_threshold_pace=lactate_pace,
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
