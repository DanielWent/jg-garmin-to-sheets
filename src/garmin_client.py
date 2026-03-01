from datetime import date, datetime, timedelta
from typing import Dict, Any, Optional, List
import asyncio, logging, json, garminconnect, garth
from pathlib import Path
from .exceptions import MFARequiredException
from .config import GarminMetrics
from statistics import mean

logger = logging.getLogger(__name__)

class GarminClient:
    def __init__(self, email, password, profile_name="default", manual_name=None, manual_dob=None, manual_gender=None):
        self.email, self.password, self.profile_name = email, password, profile_name
        self.manual_name, self.manual_dob, self.manual_gender = manual_name, manual_dob, manual_gender
        self.session_dir = Path(f"~/.garth/{self.profile_name}").expanduser()
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.token_file = self.session_dir / "tokens.json"
        self.client = garminconnect.Garmin(email, password)
        self._authenticated = False

    async def authenticate(self):
        loop = asyncio.get_event_loop()
        garth.configure(domain="garmin.com")
        if self.token_file.exists():
            try:
                with open(self.token_file, "r") as f: self.client.garth.load(json.load(f))
                self._authenticated = True
                await self._fetch_user_profile_info(); return
            except Exception: pass
        await loop.run_in_executor(None, self.client.login)
        self._authenticated = True
        await self._fetch_user_profile_info()
        # Fix: Provide path to dump
        self.client.garth.dump(str(self.session_dir))

    async def _fetch_user_profile_info(self):
        loop = asyncio.get_event_loop()
        if self.manual_name: self.user_full_name = self.manual_name
        if self.manual_gender: self.user_gender = self.manual_gender
        if self.manual_dob:
            try:
                dob = datetime.strptime(self.manual_dob, "%Y-%m-%d").date()
                self.user_age = date.today().year - dob.year - ((date.today().month, date.today().day) < (dob.month, dob.day))
            except Exception: pass
        if not self.user_full_name:
            try:
                social = await loop.run_in_executor(None, self.client.get_social_profile, self.client.display_name)
                self.user_full_name = social.get('fullName')
            except Exception: self.user_full_name = self.client.display_name

    def _find_training_load(self, data):
        if not data: return None
        stack = [data]
        while stack:
            curr = stack.pop()
            if isinstance(curr, dict):
                for k in ['dailyTrainingLoadAcute', 'acuteLoad', 'sevenDayLoad']:
                    if curr.get(k) is not None: return int(round(curr[k]))
                stack.extend(v for v in curr.values() if isinstance(v, (dict, list)))
            elif isinstance(curr, list): stack.extend(curr)
        return None

    async def get_metrics(self, target_date: date) -> GarminMetrics:
        if not self._authenticated: await self.authenticate()
        iso = target_date.isoformat()
        loop = asyncio.get_event_loop()
        async def safe(n, c):
            try: return await c
            except Exception: return None

        c_summary = safe("Sum", loop.run_in_executor(None, self.client.get_user_summary, iso))
        c_stats = safe("Stats", loop.run_in_executor(None, self.client.get_body_composition, iso, iso))
        c_sleep = safe("Sleep", loop.run_in_executor(None, self.client.get_sleep_data, iso))
        c_hrv = safe("HRV", loop.run_in_executor(None, self.client.get_hrv_data, iso))
        c_bp = safe("BP", loop.run_in_executor(None, self.client.get_blood_pressure, iso))
        c_ts_std = safe("TS", loop.run_in_executor(None, self.client.get_training_status, iso))
        c_ts_mod = safe("TSM", loop.run_in_executor(None, self.client.connectapi, f"metrics-service/metrics/trainingstatus/aggregated/{iso}"))
        c_readiness = safe("Readiness", loop.run_in_executor(None, self.client.get_training_readiness, iso))
        c_lactate = safe("Lactate", loop.run_in_executor(None, self.client.connectapi, "biometric-service/biometric/latestLactateThreshold"))

        res = await asyncio.gather(c_summary, c_stats, c_sleep, c_hrv, c_bp, c_ts_std, c_ts_mod, c_readiness, c_lactate)
        summary, stats, sleep, hrv, bp, ts_std, ts_mod, readiness, lactate = res

        summary = (summary[0] if isinstance(summary, list) and summary else summary) or {}
        sleep_dto = (sleep.get('dailySleepDTO') or sleep) if isinstance(sleep, dict) else {}
        
        # Safely handle BP list indexing
        sys = dia = None
        if bp and bp.get('measurementSummaries'):
            readings = bp['measurementSummaries'][0].get('measurements', [])
            if readings:
                sys = int(round(mean(r['systolic'] for r in readings if r.get('systolic'))))
                dia = int(round(mean(r['diastolic'] for r in readings if r.get('diastolic'))))

        # Safely handle Stats list indexing
        weight = bmi = body_fat = muscle = bone = water = visceral = None
        if stats and stats.get('dateWeightList'):
            curr_w = stats['dateWeightList'][-1]
            weight, body_fat, bmi = curr_w.get('weight', 0)/1000, curr_w.get('bodyFat'), curr_w.get('bmi')
            water, visceral = curr_w.get('bodyWater'), curr_w.get('visceralFat')
            muscle, bone = curr_w.get('muscleMass', 0)/1000, curr_w.get('boneMass', 0)/1000

        vrun = vcyc = tstat = None
        if ts_std:
            ts_std = ts_std[0] if isinstance(ts_std, list) else ts_std
            mr_vo2 = ts_std.get('mostRecentVO2Max', {})
            if mr_vo2.get('generic'): vrun = round(float(mr_vo2['generic'].get('vo2MaxPreciseValue') or 0), 1)
            if mr_vo2.get('cycling'): vcyc = round(float(mr_vo2['cycling'].get('vo2MaxPreciseValue') or 0), 1)
            ts_fb = ts_std.get('mostRecentTrainingStatus', {}).get('latestTrainingStatusData', {})
            for d in ts_fb.values(): tstat = d.get('trainingStatusFeedbackPhrase'); break

        return GarminMetrics(
            date=target_date, user_name=self.user_full_name, user_age=self.user_age, user_gender=self.user_gender,
            sleep_score=sleep_dto.get('sleepScores', {}).get('overall', {}).get('value'),
            sleep_length=round(sleep_dto.get('sleepTimeSeconds', 0)/60) if sleep_dto.get('sleepTimeSeconds') else None,
            overnight_pulse_ox=sleep_dto.get('averageSpO2Value'),
            body_battery_charged=summary.get('bodyBatteryChargedValue'),
            body_battery_drain=summary.get('bodyBatteryDrainedValue'),
            training_readiness=readiness.get('score') if isinstance(readiness, dict) else None,
            training_load_focus=ts_mod.get('trainingLoadFocus') if isinstance(ts_mod, dict) else None,
            weight=weight, bmi=bmi, body_fat=body_fat, skeletal_muscle=muscle, bone_mass=bone, body_water=water, visceral_fat=visceral,
            blood_pressure_systolic=sys, blood_pressure_diastolic=dia, resting_heart_rate=summary.get('restingHeartRate'),
            average_stress=summary.get('averageStressLevel'), body_battery_max=summary.get('bodyBatteryHighestValue'),
            body_battery_min=summary.get('bodyBatteryLowestValue'), vo2max_running=vrun, vo2max_cycling=vcyc,
            seven_day_load=self._find_training_load(ts_mod or ts_std), training_status=tstat,
            active_calories=summary.get('activeKilocalories'), resting_calories=summary.get('bmrKilocalories'),
            total_calories=(summary.get('activeKilocalories') or 0) + (summary.get('bmrKilocalories') or 0),
            steps=summary.get('totalSteps'), intensity_minutes=(summary.get('moderateIntensityMinutes', 0) or 0) + (2*(summary.get('vigorousIntensityMinutes', 0) or 0)),
            floors_climbed=round(float(summary.get('floorsAscended') or 0))
        )
