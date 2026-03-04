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

    async def authenticate(self):
        loop = asyncio.get_event_loop()
        garth.configure(domain="garmin.com")

        if self.token_file.exists():
            try:
                logger.info(f"Attempting to resume session for {self.profile_name}...")
                with open(self.token_file, "r") as f:
                    saved_tokens = json.load(f)
                
                self.client.garth.load(saved_tokens)
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

            try:
                with open(self.token_file, "w") as f:
                    json.dump(self.client.garth.dump(), f)
                logger.debug(f"Saved session tokens to {self.token_file}")
            except Exception as e:
                logger.error(f"Failed to save session tokens: {e}")

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
                if user_settings and 'userData' in user_settings:
                    dob_str = user_settings['userData'].get('birthDate')
                    if dob_str:
                        dob = datetime.strptime(dob_str, "%Y-%m-%d").date()
                        today = date.today()
                        self.user_age = round((today - dob).days / 365.25, 1)
                    
        except Exception as e:
            logger.warning(f"Error in _fetch_user_profile_info (fallback): {e}")

    async def _fetch_hrv_data(self, target_date_iso: str) -> Optional[Dict[str, Any]]:
        try:
            return await asyncio.get_event_loop().run_in_executor(
                None, self.client.get_hrv_data, target_date_iso
            )
        except Exception as e:
            logger.debug(f"Error fetching HRV data: {str(e)}")
            return None

    def _find_training_load(self, data: Any) -> Optional[int]:
        if not data: return None
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

    def _find_training_load_focus(self, data: Any) -> Optional[str]:
        if not data: return None
        stack = [data]
        while stack:
            current = stack.pop()
            if isinstance(current, dict):
                for k in ['trainingBalanceFeedbackPhrase', 'statusText']:
                    if k in current and current[k] is not None:
                        return str(current[k])
                for v in current.values():
                    if isinstance(v, (dict, list)):
                        stack.append(v)
            elif isinstance(current, list):
                for item in current:
                    if isinstance(item, (dict, list)):
                        stack.append(item)
        return None

    def _find_training_readiness(self, data: Any) -> Optional[int]:
        if not data: return None
        if isinstance(data, list) and len(data) > 0:
            for item in reversed(data):
                if isinstance(item, dict) and 'score' in item and item['score'] is not None:
                    try: return int(item['score'])
                    except (ValueError, TypeError): pass

        stack = [data]
        while stack:
            current = stack.pop()
            if isinstance(current, dict):
                for k in ['trainingReadinessScore', 'readinessScore', 'score']:
                    if k in current and current[k] is not None:
                        try: return int(current[k])
                        except (ValueError, TypeError): pass

                for v in current.values():
                    if isinstance(v, (dict, list)):
                        stack.append(v)
            elif isinstance(current, list):
                for item in current:
                    if isinstance(item, (dict, list)):
                        stack.append(item)
        return None

    def _calculate_pace(self, speed_ms: float) -> str:
        if not speed_ms or speed_ms <= 0: return ""
        try:
            sec_per_km = 1000 / speed_ms
            p_min = int(sec_per_km / 60)
            p_sec = int(sec_per_km % 60)
            return f"{p_min}:{p_sec:02d}"
        except Exception:
            return ""

    async def get_metrics(self, target_date: date) -> GarminMetrics:
        if not self._authenticated:
            if self._auth_failed: raise Exception("Authentication previously failed.")
            await self.authenticate()
        else:
            try:
                 if self.token_file.exists():
                     with open(self.token_file, "r") as f:
                         self.client.garth.load(json.load(f))
            except Exception:
                pass

        async def safe_fetch(name, coro):
            try: return await coro
            except Exception as e:
                logger.warning(f"Failed to fetch {name} for {target_date}: {e}")
                return None

        async def direct_fetch(name, endpoint):
            try: return await asyncio.get_event_loop().run_in_executor(None, self.client.connectapi, endpoint)
            except Exception as e:
                logger.debug(f"Direct fetch for {name} failed: {e}")
                return None

        try:
            target_iso = target_date.isoformat()
            loop = asyncio.get_event_loop()
            
            task_lactate_hr_url = f"biometric-service/stats/lactateThresholdHeartRate/range/{target_iso}/{target_iso}"
            task_lactate_speed_url = f"biometric-service/stats/lactateThresholdSpeed/range/{target_iso}/{target_iso}"
            lactate_params = {'aggregationStrategy': 'LATEST', 'sport': 'RUNNING'}

            c_summary = safe_fetch("User Summary", loop.run_in_executor(None, self.client.get_user_summary, target_iso))
            c_stats = safe_fetch("Stats", loop.run_in_executor(None, self.client.get_body_composition, target_iso, target_iso))
            c_sleep = safe_fetch("Sleep", loop.run_in_executor(None, self.client.get_sleep_data, target_iso))
            c_hrv = self._fetch_hrv_data(target_iso)
            c_bp = safe_fetch("Blood Pressure", loop.run_in_executor(None, self.client.get_blood_pressure, target_iso))
            c_activities = safe_fetch("Activities", loop.run_in_executor(None, self.client.get_activities_by_date, target_iso, target_iso))
            c_training_std = safe_fetch("Training Status (Std)", loop.run_in_executor(None, self.client.get_training_status, target_iso))
            
            modern_url = f"metrics-service/metrics/trainingstatus/aggregated/{target_iso}"
            c_training_modern = direct_fetch("Training Status (Modern)", modern_url)
            
            c_lactate_direct = safe_fetch("Lactate Direct", loop.run_in_executor(None, self.client.connectapi, "biometric-service/biometric/latestLactateThreshold"))
            
            c_lactate_range_hr = safe_fetch("Lactate Range HR", loop.run_in_executor(
                None, partial(self.client.connectapi, task_lactate_hr_url, params=lactate_params)
            ))
            
            c_lactate_range_speed = safe_fetch("Lactate Range Speed", loop.run_in_executor(
                None, partial(self.client.connectapi, task_lactate_speed_url, params=lactate_params)
            ))
            
            c_readiness = safe_fetch("Training Readiness", loop.run_in_executor(None, self.client.get_training_readiness, target_iso))

            results = await asyncio.gather(
                c_summary, c_stats, c_sleep, c_hrv, c_bp, c_activities, 
                c_training_std, c_training_modern, 
                c_lactate_direct, c_lactate_range_hr, c_lactate_range_speed,
                c_readiness
            )

            (summary, stats, sleep_data, hrv_payload, bp_payload, activities, 
             training_status_std, training_status_modern, 
             lactate_data, lactate_range_hr, lactate_range_speed,
             readiness_data) = results

            summary = summary or {}
            if isinstance(summary, list): summary = summary[0] if summary else {}

            sleep_data = sleep_data or {}
            if isinstance(sleep_data, list): sleep_data = sleep_data[0] if sleep_data else {}

            training_status_std = training_status_std or {}
            if isinstance(training_status_std, list): training_status_std = training_status_std[0] if training_status_std else {}

            bb_max = None
            bb_min = None
            if summary:
                bb_max = summary.get('bodyBatteryHighestValue')
                bb_min = summary.get('bodyBatteryLowestValue')

            weight = None
            body_fat = None
            bmi = None
            skeletal_muscle = None
            bone_mass = None
            body_water = None
            visceral_fat = None
            
            if stats:
                current_stats = None
                if isinstance(stats, dict) and 'dateWeightList' in stats:
                    weight_list = stats.get('dateWeightList', [])
                    if weight_list:
                        for entry in weight_list:
                             if entry.get('date') == target_iso:
                                 current_stats = entry
                                 break
                        if not current_stats:
                             current_stats = weight_list[-1]
                elif isinstance(stats, dict):
                     current_stats = stats
                elif isinstance(stats, list) and len(stats) > 0:
                     current_stats = stats[0]

                if current_stats:
                    if current_stats.get('weight'): 
                        weight = current_stats.get('weight') / 1000
                    body_fat = current_stats.get('bodyFat')
                    bmi = current_stats.get('bmi')
                    if current_stats.get('muscleMass'): 
                        skeletal_muscle = current_stats.get('muscleMass') / 1000
                    if current_stats.get('boneMass'): 
                        bone_mass = current_stats.get('boneMass') / 1000
                    body_water = current_stats.get('bodyWater')
                    visceral_fat = current_stats.get('visceralFat')

            bp_systolic = None
            bp_diastolic = None
            
            if bp_payload:
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
                        sys_values = [r['systolic'] for r in readings if isinstance(r, dict) and r.get('systolic')]
                        dia_values = [r['diastolic'] for r in readings if isinstance(r, dict) and r.get('diastolic')]
                        
                        if sys_values: bp_systolic = int(round(mean(sys_values)))
                        if dia_values: bp_diastolic = int(round(mean(dia_values)))

                except Exception as e_bp:
                    logger.error(f"[{target_date}] Error parsing Blood Pressure: {e_bp}")

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
                sleep_dto = sleep_data.get('dailySleepDTO')
                if not sleep_dto and isinstance(sleep_data, dict):
                    sleep_dto = sleep_data

                if sleep_dto:
                    sleep_scores = sleep_dto.get('sleepScores') or {}
                    sleep_score = sleep_scores.get('overall', {}).get('value')
                    
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

            overnight_hrv_value = None
            hrv_status_value = None
            if hrv_payload and hrv_payload.get('hrvSummary'):
                hrv_summary = hrv_payload['hrvSummary']
                overnight_hrv_value = hrv_summary.get('lastNightAvg')
                hrv_status_value = hrv_summary.get('status')

            FORCE_API_WEATHER_TO_CELSIUS = True

            processed_activities = []
            if activities:
                for activity in activities:
                    if not isinstance(activity, dict): continue
                    atype = activity.get('activityType') or {}
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
                        cal = activity.get('calories')
                        elev_gain = activity.get('elevationGain') 
                        elev_loss = activity.get('elevationLoss') 
                        aerobic_te = activity.get('aerobicTrainingEffect')
                        anaerobic_te = activity.get('anaerobicTrainingEffect')
                        avg_power = activity.get('avgPower') or activity.get('averageRunningPower')
                        training_effect = activity.get('trainingEffectLabel')
                        gap_speed = activity.get('avgGradeAdjustedSpeed')
                        gap_str = self._calculate_pace(gap_speed)

                        full_act = activity
                        try:
                            if hasattr(self.client, 'get_activity'):
                                fetched_act = await loop.run_in_executor(None, self.client.get_activity, act_id)
                                if fetched_act: full_act = fetched_act
                            else:
                                fetched_act = await loop.run_in_executor(None, self.client.connectapi, f"activity-service/activity/{act_id}")
                                if fetched_act: full_act = fetched_act
                        except Exception as e_full:
                            logger.debug(f"Failed to fetch full activity {act_id}: {e_full}")
                        
                        avg_cadence = full_act.get('averageRunningCadenceInStepsPerMinute') or full_act.get('averageBikingCadenceInRevPerMinute') or activity.get('averageRunningCadenceInStepsPerMinute')
                        
                        stride_length = full_act.get('avgStrideLength') or full_act.get('averageStrideLength') or full_act.get('strideLength') or activity.get('avgStrideLength') or activity.get('strideLength')
                        if stride_length and stride_length > 10:
                            stride_length = stride_length / 100
                            
                        gct = full_act.get('avgGroundContactTime') or full_act.get('averageGroundContactTime') or full_act.get('groundContactTime') or activity.get('avgGroundContactTime')
                        vertical_osc = full_act.get('avgVerticalOscillation') or full_act.get('averageVerticalOscillation') or full_act.get('verticalOscillation') or activity.get('avgVerticalOscillation')
                        
                        # --- EXTRACTING NEW METRICS ---
                        training_load = full_act.get('activityTrainingLoad') or activity.get('activityTrainingLoad')
                        max_power = full_act.get('maxPower') or activity.get('maxPower')
                        norm_power = full_act.get('normPower') or activity.get('normPower')
                        sweat_loss = full_act.get('waterEstimated') or activity.get('waterEstimated')

                        # --- FORMATTING TRAINING EFFECT ---
                        aerobic_te_val = ""
                        if aerobic_te is not None:
                            try: aerobic_te_val = round(float(aerobic_te), 1)
                            except (ValueError, TypeError): pass

                        anaerobic_te_val = ""
                        if anaerobic_te is not None:
                            try: anaerobic_te_val = round(float(anaerobic_te), 1)
                            except (ValueError, TypeError): pass

                        # --- HR ZONES ---
                        zones_dict = {f"HR Zone {i} (min)": "" for i in range(1, 6)}
                        try:
                            hr_zones = await loop.run_in_executor(None, self.client.get_activity_hr_in_timezones, act_id)
                            if hr_zones is None:
                                hr_zones = await loop.run_in_executor(None, self.client.connectapi, f"activity-service/activity/{act_id}/hrTimeInZones")
                            if hr_zones and isinstance(hr_zones, list) and len(hr_zones) > 0:
                                zones_dict = {f"HR Zone {i} (min)": 0 for i in range(1, 6)}
                                for z in hr_zones:
                                    if not isinstance(z, dict): continue
                                    z_num = z.get('zoneNumber')
                                    z_secs = z.get('secsInZone', 0)
                                    if z_num and 1 <= z_num <= 5:
                                        zones_dict[f"HR Zone {z_num} (min)"] = round(z_secs / 60, 2)
                        except Exception as e_zone:
                            logger.warning(f"Failed to fetch HR zones for {act_id}: {e_zone}")

                        # --- POWER ZONES ---
                        power_zones_dict = {f"Power Zone {i} (min)": "" for i in range(1, 6)}
                        try:
                            power_zones = await loop.run_in_executor(None, self.client.connectapi, f"activity-service/activity/{act_id}/powerTimeInZones")
                            if power_zones and isinstance(power_zones, list) and len(power_zones) > 0:
                                power_zones_dict = {f"Power Zone {i} (min)": 0 for i in range(1, 6)}
                                for z in power_zones:
                                    if not isinstance(z, dict): continue
                                    z_num = z.get('zoneNumber')
                                    z_secs = z.get('secsInZone', 0)
                                    if z_num and 1 <= z_num <= 5:
                                        power_zones_dict[f"Power Zone {z_num} (min)"] = round(z_secs / 60, 2)
                        except Exception as e_pwr_zone:
                            logger.debug(f"Failed to fetch Power zones for {act_id}: {e_pwr_zone}")

                        feels_like_temp = ""
                        weather_condition = ""
                        wind_speed_kmh = ""
                        wind_gust_kmh = ""
                        
                        try:
                            weather_data = await loop.run_in_executor(None, self.client.get_activity_weather, act_id)
                            if weather_data and isinstance(weather_data, dict):
                                raw_temp = weather_data.get('issueApparentTemp') or weather_data.get('apparentTemp') or weather_data.get('feelsLikeTemp') or weather_data.get('issueTemp') or weather_data.get('temp') or weather_data.get('temperature')
                                
                                if raw_temp is not None:
                                    try:
                                        w_temp = float(raw_temp)
                                        watch_temp_c = full_act.get('averageTemperature') or activity.get('averageTemperature')
                                        needs_conversion = False
                                        
                                        if watch_temp_c is not None:
                                            if abs(w_temp - float(watch_temp_c)) > 8:
                                                needs_conversion = True
                                        else:
                                            if FORCE_API_WEATHER_TO_CELSIUS:
                                                needs_conversion = True
                                            elif w_temp > 45 or w_temp < -15:
                                                needs_conversion = True
                                                
                                        if needs_conversion:
                                            w_temp = (w_temp - 32) * 5.0 / 9.0
                                            
                                        feels_like_temp = round(w_temp, 1)
                                    except (ValueError, TypeError):
                                        pass
                                
                                weather_type = weather_data.get('issueWeatherType') or weather_data.get('weatherTypeDTO') or {}
                                if isinstance(weather_type, dict):
                                    weather_condition = weather_type.get('desc', weather_condition)
                                    
                                raw_wind = weather_data.get('issueWindSpeed') or weather_data.get('windSpeed')
                                raw_gust = weather_data.get('issueWindGust') or weather_data.get('windGust')
                                
                                if raw_wind is not None:
                                    try: wind_speed_kmh = round(float(raw_wind), 1)
                                    except (ValueError, TypeError): pass
                                    
                                if raw_gust is not None:
                                    try: wind_gust_kmh = round(float(raw_gust), 1)
                                    except (ValueError, TypeError): pass

                        except Exception as e_weather:
                            logger.debug(f"Failed to fetch weather for {act_id}: {e_weather}")

                        activity_entry = {
                            "Activity ID": act_id,
                            "Date (YYYY-MM-DD)": target_date.isoformat(),
                            "Start Time (HH:MM)": act_time_str,
                            "Activity Type": atype.get('typeKey', 'Unknown'),
                            "Activity Name": act_name,
                            "Distance (km)": round(dist_km, 2) if dist_km else 0,
                            "Duration (min)": round(dur_min, 1) if dur_min else 0,
                            "Avg Pace (min/km)": pace_str,
                            "Average Grade Adjusted Pace (min/km)": gap_str,
                            "Total Ascent (m)": int(elev_gain) if elev_gain else "",
                            "Total Descent (m)": int(elev_loss) if elev_loss else "",
                            "Feels Like Temperature (Celsius)": feels_like_temp,
                            "Weather Condition": weather_condition,
                            "Sustained Wind Speed (km/h)": wind_speed_kmh,
                            "Avg HR (bpm)": int(avg_hr) if avg_hr else "",
                            "Max HR (bpm)": int(max_hr) if max_hr else "",
                            "Average Cadence (spm)": int(avg_cadence) if avg_cadence else "",
                            "Average Stride Length (m)": round(stride_length, 2) if stride_length else "",
                            "Average Ground Contact Time (ms)": int(gct) if gct else "",
                            "Vertical Oscillation (cm)": round(vertical_osc, 2) if vertical_osc else "",
                            "Aerobic Training Effect (0.0-5.0)": aerobic_te_val,
                            "Anaerobic Training Effect (0.0-5.0)": anaerobic_te_val,
                            "Activity Training Load": round(training_load, 1) if training_load else "",
                            "Avg Power (Watts)": int(avg_power) if avg_power else "",
                            "Max Power (Watts)": int(max_power) if max_power else "",
                            "Normalized Power (Watts)": int(norm_power) if norm_power else "",
                            "Estimated Sweat Loss (ml)": int(sweat_loss) if sweat_loss else "",
                            "Garmin Training Effect Label": training_effect if training_effect else "",
                        }
                        activity_entry.update(zones_dict)
                        activity_entry.update(power_zones_dict)
                        processed_activities.append(activity_entry)

                    except Exception as e_act:
                        logger.error(f"Error parsing activity detail: {e_act}")
                        continue

            active_cal = None
            resting_cal = None
            total_cal = None
            intensity_min = None
            resting_hr = None
            avg_stress = None
            floors = None
            bb_charged = None
            bb_drained = None
            
            if summary:
                active_cal = summary.get('activeKilocalories')
                resting_cal = summary.get('bmrKilocalories')
                if active_cal is not None or resting_cal is not None:
                    total_cal = (active_cal or 0) + (resting_cal or 0)

                intensity_min = (summary.get('moderateIntensityMinutes', 0) or 0) + (2 * (summary.get('vigorousIntensityMinutes', 0) or 0))
                resting_hr = summary.get('restingHeartRate')
                avg_stress = summary.get('averageStressLevel')
                
                bb_charged = summary.get('bodyBatteryChargedValue')
                bb_drained = summary.get('bodyBatteryDrainedValue')

                raw_floors = summary.get('floorsAscended') or summary.get('floorsClimbed')
                if raw_floors is not None:
                    try:
                        floors = round(float(raw_floors))
                    except (ValueError, TypeError):
                        floors = raw_floors

            vo2_run = None
            vo2_cycle = None
            train_phrase = None
            lactate_bpm = None
            lactate_pace = None
            train_load_focus = None

            if lactate_data:
                if 'heartRate' in lactate_data:
                    lactate_bpm = lactate_data['heartRate']
                if 'speed' in lactate_data:
                    speed_ms = lactate_data['speed']
                    lactate_pace = self._calculate_pace(speed_ms)
            
            if not lactate_bpm and lactate_range_hr and isinstance(lactate_range_hr, list):
                try:
                    last_entry = lactate_range_hr[-1] 
                    if isinstance(last_entry, dict) and 'value' in last_entry:
                             lactate_bpm = int(last_entry['value'])
                except Exception:
                    pass

            if not lactate_pace and lactate_range_speed and isinstance(lactate_range_speed, list):
                try:
                    last_entry = lactate_range_speed[-1]
                    if isinstance(last_entry, dict) and 'value' in last_entry:
                        speed_ms = last_entry['value']
                        if speed_ms and speed_ms > 0:
                            if speed_ms < 1.0: speed_ms *= 10  
                            lactate_pace = self._calculate_pace(speed_ms)
                except Exception:
                     pass

            if training_status_std:
                mr_vo2 = training_status_std.get('mostRecentVO2Max')
                if mr_vo2:
                    if mr_vo2.get('generic'): 
                        vo2_run = mr_vo2['generic'].get('vo2MaxPreciseValue', mr_vo2['generic'].get('vo2MaxValue'))
                        if vo2_run is not None:
                            try: vo2_run = round(float(vo2_run), 1)
                            except ValueError: pass
                    if mr_vo2.get('cycling'): 
                        vo2_cycle = mr_vo2['cycling'].get('vo2MaxPreciseValue', mr_vo2['cycling'].get('vo2MaxValue'))
                        if vo2_cycle is not None:
                            try: vo2_cycle = round(float(vo2_cycle), 1)
                            except ValueError: pass
                
                mr_ts = training_status_std.get('mostRecentTrainingStatus')
                if mr_ts:
                    ts_data = mr_ts.get('latestTrainingStatusData')
                    if ts_data:
                        for dev_data in ts_data.values():
                            if isinstance(dev_data, dict):
                                train_phrase = dev_data.get('trainingStatusFeedbackPhrase')
                                if train_phrase: break
                    
                    if not lactate_bpm and 'lactateThresholdHeartRate' in mr_ts:
                        lactate_bpm = mr_ts['lactateThresholdHeartRate']

            train_load_focus = self._find_training_load_focus(training_status_modern)
            if not train_load_focus:
                train_load_focus = self._find_training_load_focus(training_status_std)

            training_readiness = self._find_training_readiness(readiness_data)

            seven_day_load = None
            if training_status_modern:
                seven_day_load = self._find_training_load(training_status_modern)
            if seven_day_load is None and training_status_std:
                seven_day_load = self._find_training_load(training_status_std)
            if seven_day_load is None and summary:
                seven_day_load = self._find_training_load(summary)
                
            user_age_at_date = self.user_age
            if self.manual_dob:
                try:
                    dob = datetime.strptime(self.manual_dob, "%Y-%m-%d").date()
                    delta = target_date - dob
                    user_age_at_date = round(delta.days / 365.25, 1)
                except ValueError:
                    pass
            elif self.user_age is not None:
                user_age_at_date = float(self.user_age)

            max_hr_hunt = None
            if user_age_at_date:
                max_hr_hunt = int(round(211 - 0.64 * user_age_at_date))

            vo2_max_percentile = calculate_exact_percentile(user_age_at_date, self.user_gender, vo2_run)

            return GarminMetrics(
                date=target_date,
                user_name=self.user_full_name,
                user_age=user_age_at_date,
                user_gender=self.user_gender, 
                max_hr_hunt=max_hr_hunt,
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
                skeletal_muscle=skeletal_muscle,
                bone_mass=bone_mass,
                body_water=body_water,
                visceral_fat=visceral_fat,
                blood_pressure_systolic=bp_systolic,
                blood_pressure_diastolic=bp_diastolic,
                resting_heart_rate=resting_hr,
                average_stress=avg_stress,
                body_battery_max=bb_max,
                body_battery_min=bb_min,
                body_battery_charged=bb_charged,
                body_battery_drained=bb_drained,
                overnight_hrv=overnight_hrv_value,
                hrv_status=hrv_status_value,
                vo2max_running=vo2_run,
                vo2max_cycling=vo2_cycle,
                vo2_max_percentile=vo2_max_percentile,
                seven_day_load=seven_day_load,
                lactate_threshold_bpm=lactate_bpm,
                lactate_threshold_pace=lactate_pace,
                training_status=train_phrase,
                training_load_focus=train_load_focus,
                training_readiness=training_readiness,
                active_calories=active_cal,
                resting_calories=resting_cal,
                total_calories=total_cal,
                intensity_minutes=intensity_min,
                steps=steps,
                floors_climbed=floors,
                activities=processed_activities
            )

        except Exception as e:
            logger.error(f"Error fetching metrics for {target_date}: {str(e)}")
            return GarminMetrics(date=target_date)
