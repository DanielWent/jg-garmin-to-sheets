from datetime import date, datetime, timedelta
from typing import Dict, Any, Optional, List
import asyncio
import logging
import json
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
        if not data:
            return None
        
        stack = [data]
        while stack:
            current = stack.pop()
            
            if isinstance(current, dict):
                if 'dailyTrainingLoadAcute' in current and current['dailyTrainingLoadAcute'] is not None:
                    return int(round(current['dailyTrainingLoadAcute']))
                if 'acuteLoad' in current and current['acuteLoad'] is not None:
                    return int(round(current['acuteLoad']))
                if 'sevenDayLoad' in current and current['sevenDayLoad'] is not None:
                    return int(round(current['sevenDayLoad']))
                if 'timeInZoneLoad' in current and current['timeInZoneLoad'] is not None:
                     return int(round(current['timeInZoneLoad']))
                
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

        async def safe_fetch(name, coro):
            try:
                return await coro
            except Exception as e:
                logger.warning(f"Failed to fetch {name} for {target_date}: {e}")
                return None

        async def direct_fetch(name, endpoint):
            try:
                return await asyncio.get_event_loop().run_in_executor(
                    None, self.client.connectapi, endpoint
                )
            except Exception as e:
                logger.debug(f"Direct fetch for {name} failed: {e}")
                return None

        # --- Lactate Threshold (Specific Date Fetch) ---
        async def get_lactate_direct():
            try:
                # Request data strictly for the single target day
                # We use the Range endpoint but set start=target and end=target
                url_hr = f"biometric-service/stats/lactateThresholdHeartRate/range/{target_iso}/{target_iso}"
                url_pace = f"biometric-service/stats/lactateThresholdSpeed/range/{target_iso}/{target_iso}"
                
                hr_data, pace_data = await asyncio.gather(
                    asyncio.get_event_loop().run_in_executor(None, self.client.connectapi, url_hr),
                    asyncio.get_event_loop().run_in_executor(None, self.client.connectapi, url_pace)
                )
                
                return {"hr_list": hr_data, "pace_list": pace_data}
            except Exception as e:
                logger.debug(f"Could not fetch Lactate for {target_date}: {e}")
                return None

        try:
            target_iso = target_date.isoformat()
            loop = asyncio.get_event_loop()

            # 1. Define Tasks
            c_summary = safe_fetch("User Summary", loop.run_in_executor(None, self.client.get_user_summary, target_iso))
            c_stats = safe_fetch("Stats", loop.run_in_executor(None, self.client.get_stats_and_body, target_iso))
            c_sleep = safe_fetch("Sleep", loop.run_in_executor(None, self.client.get_sleep_data, target_iso))
            c_hrv = self._fetch_hrv_data(target_iso)
            c_bp = safe_fetch("Blood Pressure", loop.run_in_executor(None, self.client.get_blood_pressure, target_iso))
            c_activities = safe_fetch("Activities", loop.run_in_executor(None, self.client.get_activities_by_date, target_iso, target_iso))
            c_training_std = safe_fetch("Training Status (Std)", loop.run_in_executor(None, self.client.get_training_status, target_iso))
            
            modern_url = f"metrics-service/metrics/trainingstatus/aggregated/{target_iso}"
            c_training_modern = direct_fetch("Training Status (Modern)", modern_url)
            
            # UPDATED: Use the specific date fetcher
            c_lactate_direct = get_lactate_direct()

            # 2. Execute Parallel Fetch
            results = await asyncio.gather(
                c_summary, c_stats, c_sleep, c_hrv, c_bp, c_activities, 
                c_training_std, c_training_modern, c_lactate_direct
            )

            (summary, stats, sleep_data, hrv_payload, bp_payload, activities, 
             training_status_std, training_status_modern, lactate_data) = results

            # ---------------------------------------------------------
            # Body Battery Parsing
            # ---------------------------------------------------------
            bb_max = None
            bb_min = None
            if summary:
                bb_max = summary.get('bodyBatteryHighestValue')
                bb_min = summary.get('bodyBatteryLowestValue')
                logger.info(f"[{target_date}] Body Battery: Max={bb_max}, Min={bb_min}")
            else:
                logger.info(f"[{target_date}] Body Battery: No Summary Data")

            # ---------------------------------------------------------
            # Stats (Weight/Body/BMI) Parsing - WITH LOGGING
            # ---------------------------------------------------------
            weight = None
            body_fat = None
            bmi = None
            
            if stats:
                logger.info(f"[{target_date}] Raw Stats Data: {json.dumps(stats, default=str)}")
                if stats.get('weight'): 
                    weight = stats.get('weight') / 1000
                body_fat = stats.get('bodyFat')
                bmi = stats.get('bmi')
                
                logger.info(f"[{target_date}] Parsed Body Metrics -> Weight: {weight}, BMI: {bmi}, Fat: {body_fat}")
            else:
                logger.info(f"[{target_date}] Stats data is None/Empty.")

            # ---------------------------------------------------------
            # Blood Pressure Parsing - WITH LOGGING
            # ---------------------------------------------------------
            bp_systolic = None
            bp_diastolic = None
            
            if bp_payload:
                logger.info(f"[{target_date}] Raw BP Payload found (type: {type(bp_payload)})")
                readings = []
                
                try:
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
                        logger.info(f"[{target_date}] Found {len(readings)} BP readings.")
                        sys_values = [r['systolic'] for r in readings if isinstance(r, dict) and r.get('systolic')]
                        dia_values = [r['diastolic'] for r in readings if isinstance(r, dict) and r.get('diastolic')]
                        
                        if sys_values: bp_systolic = int(round(mean(sys_values)))
                        if dia_values: bp_diastolic = int(round(mean(dia_values)))
                        
                        logger.info(f"[{target_date}] Parsed BP -> Systolic: {bp_systolic}, Diastolic: {bp_diastolic}")
                    else:
                        logger.info(f"[{target_date}] No BP readings extracted from payload.")

                except Exception as e_bp:
                    logger.error(f"[{target_date}] Error parsing Blood Pressure: {e_bp}")
            else:
                logger.info(f"[{target_date}] Blood Pressure payload is None.")

            # ---------------------------------------------------------
            # Fallbacks (Steps)
            # ---------------------------------------------------------
            steps = None
            if summary:
                steps = summary.get('totalSteps')
            
            if steps is None:
                try:
                    daily_steps_data = await safe_fetch("Fallback Steps", loop.run_in_executor(None, self.client.get_daily_steps, target_iso, target_iso))
                    if daily_steps_data and isinstance(daily_steps_data, list) and len(daily_steps_data) > 0:
                        steps = daily_steps_data[0].get('totalSteps')
                except Exception:
                    pass

            # ---------------------------------------------------------
            # Standard Parsing (Sleep, HRV, Activities, etc.)
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

                        # Metrics
                        avg_power = activity.get('avgPower') or activity.get('averageRunningPower')
                        gct = activity.get('avgGroundContactTime')
                        vert_osc = activity.get('avgVerticalOscillation')
                        stride_len = activity.get('avgStrideLength')

                        # HR Zones
                        zones_dict = {
                            "HR Zone 1 (min)": 0, "HR Zone 2 (min)": 0, 
                            "HR Zone 3 (min)": 0, "HR Zone 4 (min)": 0, "HR Zone 5 (min)": 0
                        }
                        
                        try:
                            hr_zones = await loop.run_in_executor(
                                None, self.client.get_activity_hr_in_timezones, act_id
                            )
                            if hr_zones:
                                for z in hr_zones:
                                    z_num = z.get('zoneNumber')
                                    z_secs = z.get('secsInZone', 0)
                                    if z_num and 1 <= z_num <= 5:
                                        zones_dict[f"HR Zone {z_num} (min)"] = round(z_secs / 60, 2)
                        except Exception as e_zone:
                            logger.warning(f"Failed to fetch HR zones for {act_id}: {e_zone}")

                        # Build Entry
                        activity_entry = {
                            "Activity ID": act_id,
                            "Date (YYYY-MM-DD)": target_date.isoformat(),
                            "Start Time (HH:MM)": act_time_str,
                            "Activity Type": atype.get('typeKey', 'Unknown'),
                            "Activity Name": act_name,
                            "Distance (km)": round(dist_km, 2) if dist_km else 0,
                            "Duration (min)": round(dur_min, 1) if dur_min else 0,
                            "Avg Pace (min/km)": pace_str,
                            "Avg HR (bpm)": int(avg_hr) if avg_hr else "",
                            "Max HR (bpm)": int(max_hr) if max_hr else "",
                            "Total Calories (kcal)": int(cal) if cal else "",
                            "Avg Cadence (spm)": int(avg_cadence) if avg_cadence else "",
                            "Elevation Gain (m)": int(elev) if elev else "",
                            "Aerobic TE (0-5.0)": aerobic_te,
                            "Anaerobic TE (0-5.0)": anaerobic_te,
                            "Avg Power (Watts)": int(avg_power) if avg_power else "",
                            "Avg GCT (ms)": round(gct, 1) if gct else "",
                            "Avg Vert Osc (cm)": round(vert_osc, 2) if vert_osc else "",
                            "Avg Stride Len (m)": round(stride_len / 100, 2) if stride_len else "", 
                        }
                        activity_entry.update(zones_dict)
                        processed_activities.append(activity_entry)

                    except Exception as e_act:
                        logger.error(f"Error parsing activity detail: {e_act}")
                        continue

            # --- Summary Stats ---
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

            # --- Training Load & Lactate ---
            vo2_run = None
            vo2_cycle = None
            train_phrase = None
            
            # --- UPDATED PARSE LACTATE DATA (Day Specific) ---
            lactate_bpm = None
            lactate_pace = None
            
            if lactate_data:
                # 1. Parse Heart Rate
                hr_list = lactate_data.get("hr_list", [])
                if hr_list and isinstance(hr_list, list):
                    for entry in hr_list:
                        # Ensure the data belongs to this specific date
                        if entry.get('calendarDate') == target_iso:
                            lactate_bpm = entry.get('value')
                            break # Found the entry for today

                # 2. Parse Pace (Speed)
                pace_list = lactate_data.get("pace_list", [])
                if pace_list and isinstance(pace_list, list):
                    for entry in pace_list:
                        if entry.get('calendarDate') == target_iso:
                            speed_mps = entry.get('value') # meters/second
                            
                            if speed_mps and speed_mps > 0:
                                try:
                                    # Convert m/s to min/km
                                    seconds_per_km = 1000 / speed_mps
                                    minutes = int(seconds_per_km // 60)
                                    seconds = int(seconds_per_km % 60)
                                    lactate_pace = f"{minutes}:{seconds:02d} / km"
                                except Exception:
                                    lactate_pace = None
                            break

            if training_status_modern:
                seven_day_load = self._find_training_load(training_status_modern)
            if seven_day_load is None and training_status_std:
                seven_day_load = self._find_training_load(training_status_std)
            if seven_day_load is None and summary:
                seven_day_load = self._find_training_load(summary)

            if training_status_std:
                mr_vo2 = training_status_std.get('mostRecentVO2Max', {})
                if mr_vo2.get('generic'): vo2_run = mr_vo2['generic'].get('vo2MaxValue')
                if mr_vo2.get('cycling'): vo2_cycle = mr_vo2['cycling'].get('vo2MaxValue')

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
                body_battery_max=bb_max,
                body_battery_min=bb_min,
                overnight_hrv=overnight_hrv_value,
                hrv_status=hrv_status_value,
                vo2max_running=vo2_run,
                vo2max_cycling=vo2_cycle,
                seven_day_load=seven_day_load,
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
