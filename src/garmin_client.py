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
            await self._fetch_user_profile_info()
            try:
                with open(self.token_file, "w") as f:
                    json.dump(self.client.garth.dump(), f)
            except Exception as e:
                logger.error(f"Failed to save session tokens: {e}")
        except Exception as e:
            logger.error(f"Authentication error: {str(e)}")
            raise garminconnect.GarminConnectAuthenticationError(f"Authentication error: {str(e)}") from e

    async def _fetch_user_profile_info(self):
        loop = asyncio.get_event_loop()
        if self.manual_name: self.user_full_name = self.manual_name
        if self.manual_gender: self.user_gender = self.manual_gender
        if self.manual_dob:
            try:
                dob = datetime.strptime(self.manual_dob, "%Y-%m-%d").date()
                today = date.today()
                self.user_age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
            except ValueError:
                logger.warning(f"Invalid format for USER_DOB: {self.manual_dob}.")

        try:
            if not self.user_full_name:
                display_name = self.client.display_name
                if display_name:
                    social_profile = await loop.run_in_executor(None, self.client.get_social_profile, display_name)
                    if social_profile: self.user_full_name = social_profile.get('fullName')
            if not self.user_age:
                user_settings = await loop.run_in_executor(None, self.client.get_user_settings)
                if user_settings and 'userData' in user_settings:
                    dob_str = user_settings['userData'].get('birthDate')
                    if dob_str:
                        dob = datetime.strptime(dob_str, "%Y-%m-%d").date()
                        today = date.today()
                        self.user_age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
        except Exception as e:
            logger.warning(f"Error in _fetch_user_profile_info: {e}")

    async def _fetch_hrv_data(self, target_date_iso: str) -> Optional[Dict[str, Any]]:
        try:
            return await asyncio.get_event_loop().run_in_executor(None, self.client.get_hrv_data, target_date_iso)
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
                for value in current.values():
                    if isinstance(value, (dict, list)): stack.append(value)
            elif isinstance(current, list):
                for item in current:
                    if isinstance(item, (dict, list)): stack.append(item)
        return None

    def _calculate_pace(self, speed_ms: float) -> str:
        if not speed_ms or speed_ms <= 0: return ""
        try:
            sec_per_km = 1000 / speed_ms
            p_min = int(sec_per_km / 60)
            p_sec = int(sec_per_km % 60)
            return f"{p_min}:{p_sec:02d}"
        except Exception: return ""

    async def get_metrics(self, target_date: date) -> GarminMetrics:
        if not self._authenticated:
            if self._auth_failed: raise Exception("Authentication previously failed.")
            await self.authenticate()

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
            
            c_summary = safe_fetch("User Summary", loop.run_in_executor(None, self.client.get_user_summary, target_iso))
            c_stats = safe_fetch("Stats", loop.run_in_executor(None, self.client.get_body_composition, target_iso, target_iso))
            c_sleep = safe_fetch("Sleep", loop.run_in_executor(None, self.client.get_sleep_data, target_iso))
            c_hrv = self._fetch_hrv_data(target_iso)
            c_bp = safe_fetch("Blood Pressure", loop.run_in_executor(None, self.client.get_blood_pressure, target_iso))
            c_activities = safe_fetch("Activities", loop.run_in_executor(None, self.client.get_activities_by_date, target_iso, target_iso))
            c_training_std = safe_fetch("Training Status (Std)", loop.run_in_executor(None, self.client.get_training_status, target_iso))
            c_readiness = safe_fetch("Readiness", loop.run_in_executor(None, self.client.get_training_readiness, target_iso))
            
            modern_url = f"metrics-service/metrics/trainingstatus/aggregated/{target_iso}"
            c_training_modern = direct_fetch("Training Status (Modern)", modern_url)
            c_lactate_direct = safe_fetch("Lactate Direct", loop.run_in_executor(None, self.client.connectapi, "biometric-service/biometric/latestLactateThreshold"))

            results = await asyncio.gather(
                c_summary, c_stats, c_sleep, c_hrv, c_bp, c_activities, 
                c_training_std, c_training_modern, c_lactate_direct, c_readiness
            )

            (summary, stats, sleep_data, hrv_payload, bp_payload, activities, 
             training_status_std, training_status_modern, lactate_data, readiness_data) = results

            summary = summary or {}
            if isinstance(summary, list): summary = summary[0] if summary else {}
            sleep_data = sleep_data or {}
            if isinstance(sleep_data, list): sleep_data = sleep_data[0] if sleep_data else {}

            bb_max = bb_min = bb_charged = bb_drain = None
            if summary:
                bb_max = summary.get('bodyBatteryHighestValue')
                bb_min = summary.get('bodyBatteryLowestValue')
                bb_charged = summary.get('bodyBatteryChargedValue')
                bb_drain = summary.get('bodyBatteryDrainedValue')

            weight = body_fat = bmi = muscle = bone = water = visceral = None
            if stats:
                current_stats = stats.get('dateWeightList', [{}])[-1] if 'dateWeightList' in stats else stats
                if current_stats:
                    if current_stats.get('weight'): weight = current_stats.get('weight') / 1000
                    body_fat = current_stats.get('bodyFat')
                    bmi = current_stats.get('bmi')
                    if current_stats.get('muscleMass'): muscle = current_stats.get('muscleMass') / 1000
                    if current_stats.get('boneMass'): bone = current_stats.get('boneMass') / 1000
                    water = current_stats.get('bodyWater')
                    visceral = current_stats.get('visceralFat')

            bp_systolic = bp_diastolic = None
            if bp_payload:
                readings = bp_payload.get('measurementSummaries', [{}])[0].get('measurements', []) if 'measurementSummaries' in bp_payload else []
                if readings:
                    sys_vals = [r['systolic'] for r in readings if r.get('systolic')]
                    dia_vals = [r['diastolic'] for r in readings if r.get('diastolic')]
                    if sys_vals: bp_systolic = int(round(mean(sys_vals)))
                    if dia_vals: bp_diastolic = int(round(mean(dia_vals)))

            steps = summary.get('totalSteps') if summary else None
            sleep_score = sleep_length = sleep_need = sleep_efficiency = None
            sleep_start = sleep_end = sleep_deep = sleep_light = sleep_rem = sleep_awake = None
            respiration = pulse_ox = None

            sleep_dto = sleep_data.get('dailySleepDTO') or sleep_data
            if sleep_dto and isinstance(sleep_dto, dict):
                sleep_score = sleep_dto.get('sleepScores', {}).get('overall', {}).get('value')
                sleep_need = sleep_dto.get('sleepNeed', {}).get('actual') if isinstance(sleep_dto.get('sleepNeed'), dict) else sleep_dto.get('sleepNeed')
                respiration = sleep_dto.get('averageRespirationValue')
                pulse_ox = sleep_dto.get('averageSpO2Value')
                if sleep_dto.get('sleepTimeSeconds'): sleep_length = round(sleep_dto['sleepTimeSeconds'] / 60)
                if sleep_dto.get('sleepStartTimestampLocal'): sleep_start = datetime.fromtimestamp(sleep_dto['sleepStartTimestampLocal']/1000).strftime('%H:%M')
                if sleep_dto.get('sleepEndTimestampLocal'): sleep_end = datetime.fromtimestamp(sleep_dto['sleepEndTimestampLocal']/1000).strftime('%H:%M')
                sleep_deep = (sleep_dto.get('deepSleepSeconds') or 0) / 60
                sleep_light = (sleep_dto.get('lightSleepSeconds') or 0) / 60
                sleep_rem = (sleep_dto.get('remSleepSeconds') or 0) / 60
                sleep_awake = (sleep_dto.get('awakeSleepSeconds') or 0) / 60
                if sleep_dto.get('sleepTimeSeconds') and sleep_dto['sleepTimeSeconds'] > 0:
                    sleep_efficiency = round(((sleep_dto['sleepTimeSeconds'] - (sleep_dto.get('awakeSleepSeconds') or 0)) / sleep_dto['sleepTimeSeconds']) * 100)

            hrv_val = hrv_stat = None
            if hrv_payload and hrv_payload.get('hrvSummary'):
                hrv_val = hrv_payload['hrvSummary'].get('lastNightAvg')
                hrv_stat = hrv_payload['hrvSummary'].get('status')

            active_cal = resting_cal = total_cal = intensity_min = resting_hr = avg_stress = floors = None
            if summary:
                active_cal = summary.get('activeKilocalories')
                resting_cal = summary.get('bmrKilocalories')
                if active_cal is not None or resting_cal is not None: total_cal = (active_cal or 0) + (resting_cal or 0)
                intensity_min = (summary.get('moderateIntensityMinutes', 0) or 0) + (2 * (summary.get('vigorousIntensityMinutes', 0) or 0))
                resting_hr = summary.get('restingHeartRate')
                avg_stress = summary.get('averageStressLevel')
                raw_floors = summary.get('floorsAscended') or summary.get('floorsClimbed')
                if raw_floors: floors = round(float(raw_floors))

            vo2_run = vo2_cycle = train_phrase = lactate_bpm = lactate_pace = None
            train_focus = None
            if training_status_std:
                mr_vo2 = training_status_std.get('mostRecentVO2Max')
                if mr_vo2:
                    if mr_vo2.get('generic'): vo2_run = round(float(mr_vo2['generic'].get('vo2MaxPreciseValue') or mr_vo2['generic'].get('vo2MaxValue')), 1)
                    if mr_vo2.get('cycling'): vo2_cycle = round(float(mr_vo2['cycling'].get('vo2MaxPreciseValue') or mr_vo2['cycling'].get('vo2MaxValue')), 1)
                mr_ts = training_status_std.get('mostRecentTrainingStatus')
                if mr_ts:
                    ts_data = mr_ts.get('latestTrainingStatusData', {})
                    for dev_data in ts_data.values():
                        train_phrase = dev_data.get('trainingStatusFeedbackPhrase')
                        break
            
            if training_status_modern:
                train_focus = training_status_modern.get('trainingLoadFocus')

            readiness_score = readiness_data.get('score') if readiness_data else None

            return GarminMetrics(
                date=target_date, user_name=self.user_full_name, user_age=self.user_age, user_gender=self.user_gender,
                sleep_score=sleep_score, sleep_need=sleep_need, sleep_efficiency=sleep_efficiency, sleep_length=sleep_length,
                sleep_start_time=sleep_start, sleep_end_time=sleep_end, sleep_deep=sleep_deep, sleep_light=sleep_light,
                sleep_rem=sleep_rem, sleep_awake=sleep_awake, overnight_respiration=respiration, overnight_pulse_ox=pulse_ox,
                weight=weight, bmi=bmi, body_fat=body_fat, skeletal_muscle=muscle, bone_mass=bone, body_water=water, visceral_fat=visceral,
                blood_pressure_systolic=bp_systolic, blood_pressure_diastolic=bp_diastolic, resting_heart_rate=resting_hr,
                average_stress=avg_stress, body_battery_max=bb_max, body_battery_min=bb_min, 
                body_battery_charged=bb_charged, body_battery_drain=bb_drain,
                overnight_hrv=hrv_val, hrv_status=hrv_stat, vo2max_running=vo2_run, vo2max_cycling=vo2_cycle,
                seven_day_load=self._find_training_load(training_status_modern or training_status_std),
                training_status=train_phrase, training_readiness=readiness_score, training_load_focus=train_focus,
                active_calories=active_cal, resting_calories=resting_cal, total_calories=total_cal,
                intensity_minutes=intensity_min, steps=steps, floors_climbed=floors,
                activities=[] # Simplified for this snippet
            )
        except Exception as e:
            logger.error(f"Error fetching metrics for {target_date}: {str(e)}")
            return GarminMetrics(date=target_date)
