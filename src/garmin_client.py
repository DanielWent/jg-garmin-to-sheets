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
                for value in current.values():
                    if isinstance(value, (dict, list)):
                        stack.append(value)
            elif isinstance(current, list):
                for item in current:
                    if isinstance(item, (dict, list)):
                        stack.append(item)
        return None

    def _calculate_pace(self, speed_ms: float) -> str:
        if not speed_ms or speed_ms <= 0:
            return ""
        try:
            sec_per_km = 1000 / speed_ms
            p_min = int(sec_per_km / 60)
            p_sec = int(sec_per_km % 60)
            return f"{p_min}:{p_sec:02d}"
        except Exception:
            return ""

    async def get_metrics(self, target_date: date) -> GarminMetrics:
        if not self._authenticated:
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

        try:
            target_iso = target_date.isoformat()
            loop = asyncio.get_event_loop()
            
            task_lactate_hr_url = f"biometric-service/stats/lactateThresholdHeartRate/range/{target_iso}/{target_iso}"
            task_lactate_speed_url = f"biometric-service/stats/lactateThresholdSpeed/range/{target_iso}/{target_iso}"
            lactate_params = {'aggregationStrategy': 'LATEST', 'sport': 'RUNNING'}

            c_summary = safe_fetch("User Summary", loop.run_in_executor(None, self.client.get_user_summary, target_iso))
            c_stats = safe_fetch("Stats", loop.run_in_executor(None, self.client.get_stats_and_body, target_iso))
            c_sleep = safe_fetch("Sleep", loop.run_in_executor(None, self.client.get_sleep_data, target_iso))
            c_hrv = self._fetch_hrv_data(target_iso)
            c_bp = safe_fetch("Blood Pressure", loop.run_in_executor(None, self.client.get_blood_pressure, target_iso))
            c_activities = safe_fetch("Activities", loop.run_in_executor(None, self.client.get_activities_by_date, target_iso, target_iso))
            c_training_std = safe_fetch("Training Status (Std)", loop.run_in_executor(None, self.client.get_training_status, target_iso))
            
            modern_url = f"metrics-service/metrics/trainingstatus/aggregated/{target_iso}"
            c_training_modern = direct_fetch("Training Status (Modern)", modern_url)
            c_lactate_direct = safe_fetch("Lactate Direct", loop.run_in_executor(None, self.client.connectapi, "biometric-service/biometric/latestLactateThreshold"))
            c_lactate_range_hr = safe_fetch("Lactate Range HR", loop.run_in_executor(None, partial(self.client.connectapi, task_lactate_hr_url, params=lactate_params)))
            c_lactate_range_speed = safe_fetch("Lactate Range Speed", loop.run_in_executor(None, partial(self.client.connectapi, task_lactate_speed_url, params=lactate_params)))

            results = await asyncio.gather(
                c_summary, c_stats, c_sleep, c_hrv, c_bp, c_activities, 
                c_training_std, c_training_modern, 
                c_lactate_direct, c_lactate_range_hr, c_lactate_range_speed
            )

            (summary, stats, sleep_data, hrv_payload, bp_payload, activities, 
             training_status_std, training_status_modern, 
             lactate_data, lactate_range_hr, lactate_range_speed) = results

            bb_max = summary.get('bodyBatteryHighestValue') if summary else None
            bb_min = summary.get('bodyBatteryLowestValue') if summary else None

            # --- Safe Body Parsing ---
            weight = body_fat = bmi = skeletal_muscle = bone_mass = body_water = visceral_fat = None
            
            # Handle stats if returned as a list
            body_dict = None
            if isinstance(stats, list) and len(stats) > 0:
                body_dict = stats[0]
            elif isinstance(stats, dict):
                body_dict = stats

            if body_dict:
                if body_dict.get('weight'): weight = body_dict.get('weight') / 1000
                body_fat = body_dict.get('bodyFat')
                bmi = body_dict.get('bmi')
                if body_dict.get('muscleMass'): skeletal_muscle = body_dict.get('muscleMass') / 1000
                if body_dict.get('boneMass'): bone_mass = body_dict.get('boneMass') / 1000
                body_water = body_dict.get('bodyWater')
                visceral_fat = body_dict.get('visceralFat')

            bp_systolic = bp_diastolic = None
            if bp_payload:
                try:
                    readings = []
                    if isinstance(bp_payload, dict) and 'measurementSummaries' in bp_payload:
                        summaries = bp_payload.get('measurementSummaries', [])
                        for s_item in summaries:
                            if 'measurements' in s_item: readings.extend(s_item['measurements'])
                    elif isinstance(bp_payload, list): readings = bp_payload
                    if readings:
                        sys_v = [r['systolic'] for r in readings if r.get('systolic')]
                        dia_v = [r['diastolic'] for r in readings if r.get('diastolic')]
                        if sys_v: bp_systolic = int(round(mean(sys_v)))
                        if dia_v: bp_diastolic = int(round(mean(dia_v)))
                except Exception: pass

            steps = summary.get('totalSteps') if summary else None
            
            # Sleep parsing
            sleep_score = sleep_length = sleep_need = sleep_efficiency = None
            sleep_start_time = sleep_end_time = sleep_deep = sleep_light = None
            sleep_rem = sleep_awake = overnight_respiration = overnight_pulse_ox = None

            if sleep_data:
                sdto = sleep_data.get('dailySleepDTO', {})
                if sdto:
                    sleep_score = sdto.get('sleepScores', {}).get('overall', {}).get('value')
                    sn = sdto.get('sleepNeed')
                    sleep_need = sn.get('actual') if isinstance(sn, dict) else sn
                    overnight_respiration = sdto.get('averageRespirationValue')
                    overnight_pulse_ox = sdto.get('averageSpO2Value')
                    st_sec = sdto.get('sleepTimeSeconds')
                    if st_sec: sleep_length = round(st_sec / 60)
                    sts_l = sdto.get('sleepStartTimestampLocal')
                    ets_l = sdto.get('sleepEndTimestampLocal')
                    if sts_l: sleep_start_time = datetime.fromtimestamp(sts_l/1000).strftime('%H:%M')
                    if ets_l: sleep_end_time = datetime.fromtimestamp(ets_l/1000).strftime('%H:%M')
                    sleep_deep = (sdto.get('deepSleepSeconds') or 0) / 60
                    sleep_light = (sdto.get('lightSleepSeconds') or 0) / 60
                    sleep_rem = (sdto.get('remSleepSeconds') or 0) / 60
                    sleep_awake = (sdto.get('awakeSleepSeconds') or 0) / 60
                    if st_sec and st_sec > 0:
                        aw_sec = sdto.get('awakeSleepSeconds') or 0
                        sleep_efficiency = round(((st_sec - aw_sec) / st_sec) * 100)

            # HRV and Activities
            overnight_hrv_v = hrv_status_v = None
            if hrv_payload and 'hrvSummary' in hrv_payload:
                overnight_hrv_v = hrv_payload['hrvSummary'].get('lastNightAvg')
                hrv_status_v = hrv_payload['hrvSummary'].get('status')

            processed_activities = []
            if activities:
                for act in activities:
                    try:
                        act_id = act.get('activityId')
                        d_km = (act.get('distance') or 0) / 1000
                        d_min = (act.get('duration') or 0) / 60
                        pace_s = self._calculate_pace(act.get('averageSpeed'))
                        gap_s = self._calculate_pace(act.get('avgGradeAdjustedSpeed'))
                        z_dict = {f"HR Zone {i} (min)": 0 for i in range(1, 6)}
                        try:
                            hz = await loop.run_in_executor(None, self.client.get_activity_hr_in_timezones, act_id)
                            if hz:
                                for z in hz:
                                    zn, zs = z.get('zoneNumber'), z.get('secsInZone', 0)
                                    if zn and 1 <= zn <= 5: z_dict[f"HR Zone {zn} (min)"] = round(zs/60, 2)
                        except Exception: pass
                        entry = {
                            "Activity ID": act_id,
                            "Date (YYYY-MM-DD)": target_iso,
                            "Activity Type": act.get('activityType', {}).get('typeKey'),
                            "Distance (km)": round(d_km, 2),
                            "Duration (min)": round(d_min, 1),
                            "Avg Pace (min/km)": pace_s,
                            "Average Grade Adjusted Pace (min/km)": gap_s,
                            "Avg HR (bpm)": act.get('averageHR'),
                            "Max HR (bpm)": act.get('maxHR'),
                            "Total Ascent (m)": act.get('elevationGain'),
                            "Total Descent (m)": act.get('elevationLoss'),
                            "Aerobic TE (0-5.0)": act.get('aerobicTrainingEffect'),
                            "Anaerobic TE (0-5.0)": act.get('anaerobicTrainingEffect'),
                            "Avg Power (Watts)": act.get('avgPower') or act.get('averageRunningPower'),
                            "Garmin Training Effect Label": act.get('trainingEffectLabel'),
                        }
                        entry.update(z_dict)
                        processed_activities.append(entry)
                    except Exception: continue

            # Summary stats
            active_cal = resting_cal = intensity_min = resting_hr = avg_stress = floors = None
            rsd = lsd = msd = hsd = None
            if summary:
                active_cal = summary.get('activeKilocalories')
                resting_cal = summary.get('bmrKilocalories')
                intensity_min = (summary.get('moderateIntensityMinutes', 0) or 0) + (2 * (summary.get('vigorousIntensityMinutes', 0) or 0))
                resting_hr = summary.get('restingHeartRate')
                avg_stress = summary.get('averageStressLevel')
                if summary.get('restStressDuration'): rsd = int(round(summary['restStressDuration']/60))
                if summary.get('lowStressDuration'): lsd = int(round(summary['lowStressDuration']/60))
                if summary.get('mediumStressDuration'): msd = int(round(summary['mediumStressDuration']/60))
                if summary.get('highStressDuration'): hsd = int(round(summary['highStressDuration']/60))
                rf = summary.get('floorsAscended') or summary.get('floorsClimbed')
                if rf is not None: floors = round(float(rf))

            vo2_r = train_p = l_bpm = l_pace = None
            if lactate_data:
                l_bpm = lactate_data.get('heartRate')
                l_pace = self._calculate_pace(lactate_data.get('speed'))
            if training_status_std:
                mrv = training_status_std.get('mostRecentVO2Max', {})
                vo2_r = mrv.get('generic', {}).get('vo2MaxValue')
                tsf = training_status_std.get('mostRecentTrainingStatus', {}).get('latestTrainingStatusData', {})
                for v in tsf.values():
                    train_p = v.get('trainingStatusFeedbackPhrase')
                    break
            seven_day_load = self._find_training_load(training_status_modern or training_status_std or summary)

            return GarminMetrics(
                date=target_date,
                sleep_score=sleep_score, sleep_need=sleep_need, sleep_efficiency=sleep_efficiency,
                sleep_length=sleep_length, sleep_start_time=sleep_start_time, sleep_end_time=sleep_end_time,
                sleep_deep=sleep_deep, sleep_light=sleep_light, sleep_rem=sleep_rem, sleep_awake=sleep_awake,
                overnight_respiration=overnight_respiration, overnight_pulse_ox=overnight_pulse_ox,
                weight=weight, bmi=bmi, body_fat=body_fat, skeletal_muscle=skeletal_muscle,
                bone_mass=bone_mass, body_water=body_water, visceral_fat=visceral_fat,
                blood_pressure_systolic=bp_systolic, blood_pressure_diastolic=bp_diastolic,
                resting_heart_rate=resting_hr, average_stress=avg_stress,
                rest_stress_duration=rsd, low_stress_duration=lsd, medium_stress_duration=msd, high_stress_duration=hsd,
                body_battery_max=bb_max, body_battery_min=bb_min, overnight_hrv=overnight_hrv_v,
                hrv_status=hrv_status_v, vo2max_running=vo2_r, seven_day_load=seven_day_load,
                lactate_threshold_bpm=l_bpm, lactate_threshold_pace=l_pace, training_status=train_p,
                active_calories=active_cal, resting_calories=resting_cal, intensity_minutes=intensity_min,
                steps=steps, floors_climbed=floors, activities=processed_activities
            )
        except Exception as e:
            logger.error(f"Error fetching metrics for {target_date}: {str(e)}")
            return GarminMetrics(date=target_date)
