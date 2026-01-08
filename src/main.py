def aggregate_monthly_metrics(metrics: list[GarminMetrics], month_date: date) -> Optional[GarminMetrics]:
    """
    Takes a list of daily GarminMetrics and returns a single GarminMetrics object
    containing the average of all numeric fields.
    """
    if not metrics:
        return None

    # Helper to calculate average of a specific attribute, ignoring None values
    def get_avg(attr_name):
        values = [getattr(m, attr_name) for m in metrics if getattr(m, attr_name) is not None]
        return round(mean(values), 2) if values else None

    # Helper to cast average to int
    def get_avg_int(attr_name):
        val = get_avg(attr_name)
        return int(val) if val is not None else None

    # --- Helper to calculate average TIME strings (HH:MM) ---
    def get_avg_time(attr_name, is_start_time=False):
        minutes_list = []
        for m in metrics:
            val = getattr(m, attr_name)
            if val and isinstance(val, str) and ":" in val:
                try:
                    hh, mm = map(int, val.split(':'))
                    total_min = hh * 60 + mm
                    
                    # Logic for sleep start crossing midnight
                    if is_start_time and total_min < 12 * 60:
                        total_min += 24 * 60
                        
                    minutes_list.append(total_min)
                except ValueError:
                    continue

        if not minutes_list:
            return None

        avg_min = mean(minutes_list)
        
        # Normalize back to 0-24h range if we added 24h
        if avg_min >= 24 * 60:
            avg_min -= 24 * 60
            
        # Convert back to HH:MM
        avg_hh = int(avg_min // 60)
        avg_mm = int(round(avg_min % 60))
        
        # Handle rounding edge case
        if avg_mm == 60:
            avg_hh += 1
            avg_mm = 0
        if avg_hh >= 24:
            avg_hh -= 24
            
        return f"{avg_hh:02d}:{avg_mm:02d}"

    return GarminMetrics(
        date=month_date,  # This will be the 1st of the month
        
        # Averages
        sleep_score=get_avg("sleep_score"),
        sleep_length=get_avg("sleep_length"),
        
        # --- Time Averages ---
        sleep_start_time=get_avg_time("sleep_start_time", is_start_time=True),
        sleep_end_time=get_avg_time("sleep_end_time", is_start_time=False),
        
        sleep_need=get_avg_int("sleep_need"),
        sleep_efficiency=get_avg("sleep_efficiency"),
        sleep_deep=get_avg("sleep_deep"),
        sleep_light=get_avg("sleep_light"),
        sleep_rem=get_avg("sleep_rem"),
        sleep_awake=get_avg("sleep_awake"),
        overnight_respiration=get_avg("overnight_respiration"),
        overnight_pulse_ox=get_avg("overnight_pulse_ox"),
        weight=get_avg("weight"),
        bmi=get_avg("bmi"),
        body_fat=get_avg("body_fat"),
        blood_pressure_systolic=get_avg_int("blood_pressure_systolic"),
        blood_pressure_diastolic=get_avg_int("blood_pressure_diastolic"),
        resting_heart_rate=get_avg_int("resting_heart_rate"),
        average_stress=get_avg_int("average_stress"),
        rest_stress_duration=get_avg_int("rest_stress_duration"),
        low_stress_duration=get_avg_int("low_stress_duration"),
        medium_stress_duration=get_avg_int("medium_stress_duration"),
        high_stress_duration=get_avg_int("high_stress_duration"),
        overnight_hrv=get_avg_int("overnight_hrv"),
        vo2max_running=get_avg("vo2max_running"),
        vo2max_cycling=get_avg("vo2max_cycling"),
        
        # --- NEW: Lactate Threshold Averages ---
        lactate_threshold_bpm=get_avg_int("lactate_threshold_bpm"),
        lactate_threshold_pace=get_avg_time("lactate_threshold_pace"),
        # ---------------------------------------

        active_calories=get_avg_int("active_calories"),
        resting_calories=get_avg_int("resting_calories"),
        intensity_minutes=get_avg_int("intensity_minutes"),
        steps=get_avg_int("steps"),
        floors_climbed=get_avg("floors_climbed"),

        # Non-numeric placeholders
        training_status="Monthly Avg",
        hrv_status="Monthly Avg",
        activities=[] 
    )
