from dataclasses import dataclass, field
from datetime import date
from typing import List, Optional, Any

@dataclass
class GarminMetrics:
    date: date
    # ... (existing fields)
    sleep_score: Optional[int] = None
    sleep_need: Optional[int] = None
    sleep_efficiency: Optional[int] = None
    sleep_length: Optional[int] = None
    sleep_start_time: Optional[str] = None
    sleep_end_time: Optional[str] = None
    sleep_deep: Optional[float] = None
    sleep_light: Optional[float] = None
    sleep_rem: Optional[float] = None
    sleep_awake: Optional[float] = None
    overnight_respiration: Optional[float] = None
    overnight_pulse_ox: Optional[float] = None
    weight: Optional[float] = None
    bmi: Optional[float] = None
    body_fat: Optional[float] = None
    blood_pressure_systolic: Optional[int] = None
    blood_pressure_diastolic: Optional[int] = None
    resting_heart_rate: Optional[int] = None
    average_stress: Optional[int] = None
    rest_stress_duration: Optional[int] = None
    low_stress_duration: Optional[int] = None
    medium_stress_duration: Optional[int] = None
    high_stress_duration: Optional[int] = None
    overnight_hrv: Optional[int] = None
    hrv_status: Optional[str] = None
    vo2max_running: Optional[float] = None
    vo2max_cycling: Optional[float] = None
    lactate_threshold_bpm: Optional[int] = None   # <--- NEW
    lactate_threshold_pace: Optional[str] = None  # <--- NEW
    training_status: Optional[str] = None
    active_calories: Optional[int] = None
    resting_calories: Optional[int] = None
    intensity_minutes: Optional[int] = None
    steps: Optional[int] = None
    floors_climbed: Optional[float] = None
    activities: List[Any] = field(default_factory=list)
