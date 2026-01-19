# ... (Imports)

    async def get_metrics(self, target_date: date) -> GarminMetrics:
        # ... (Authentication and setup) ...

        try:
            target_iso = target_date.isoformat()
            loop = asyncio.get_event_loop()

            # ... (Define Tasks - same as before) ...

            results = await asyncio.gather(...) 
            # (Unpack results)

            # ---------------------------------------------------------
            # NEW: Body Battery Parsing
            # ---------------------------------------------------------
            bb_max = None
            bb_min = None
            if summary:
                bb_max = summary.get('bodyBatteryHighestValue')
                bb_min = summary.get('bodyBatteryLowestValue')
                
                # EXPLICIT LOGGING
                logger.info(f"Body Battery for {target_date}: Max={bb_max}, Min={bb_min}")
            else:
                logger.info(f"Body Battery for {target_date}: No Summary Data Found")


            # ... (Sleep, HRV, Stats logic - same as before) ...

            # ---------------------------------------------------------
            # UPDATED: Activities Parsing
            # ---------------------------------------------------------
            processed_activities = []
            if activities:
                for activity in activities:
                    try:
                        act_id = activity.get('activityId')
                        act_name = activity.get('activityName')
                        
                        # ... (Existing basic parsing) ...

                        # --- NEW METRICS ---
                        # Power
                        avg_power = activity.get('avgPower')
                        if avg_power is None:
                            avg_power = activity.get('averageRunningPower') # fallback
                        
                        # Run Dynamics
                        gct = activity.get('avgGroundContactTime')
                        vert_osc = activity.get('avgVerticalOscillation')
                        stride_len = activity.get('avgStrideLength')

                        # EXPLICIT LOGGING (Metrics)
                        logger.info(f"Activity {act_id} ({act_name}) Metrics: "
                                    f"Power={avg_power}, GCT={gct}, VO={vert_osc}, Stride={stride_len}")

                        # --- NEW: HR ZONES ---
                        # We need to fetch zone data separately for each activity
                        zones_dict = {"Zone 1 (min)": 0, "Zone 2 (min)": 0, "Zone 3 (min)": 0, "Zone 4 (min)": 0, "Zone 5 (min)": 0}
                        
                        try:
                            # Fetch zone data
                            # Note: This is a synchronous call in the library, so we wrap it
                            hr_zones = await loop.run_in_executor(
                                None, self.client.get_activity_hr_in_timezones, act_id
                            )
                            
                            if hr_zones:
                                logger.info(f"Activity {act_id} HR Zones Raw: {json.dumps(hr_zones)}")
                                # Parse the zone list. Usually looks like [{'zoneNumber': 1, 'secsInZone': 60}, ...]
                                for z in hr_zones:
                                    z_num = z.get('zoneNumber')
                                    z_secs = z.get('secsInZone', 0)
                                    if z_num and 1 <= z_num <= 5:
                                        zones_dict[f"Zone {z_num} (min)"] = round(z_secs / 60, 2)
                            else:
                                logger.info(f"Activity {act_id}: No HR Zone data returned.")

                        except Exception as e_zone:
                            logger.warning(f"Failed to fetch HR zones for {act_id}: {e_zone}")

                        # Construct the final dict
                        activity_entry = {
                            "Activity ID": act_id,
                            # ... (Existing fields) ...
                            "Avg Power": int(avg_power) if avg_power else "",
                            "GCT (ms)": round(gct, 1) if gct else "",
                            "Vert Osc (cm)": round(vert_osc, 2) if vert_osc else "",
                            "Stride Len (m)": round(stride_len / 100, 2) if stride_len else "", # Stride is often in cm, verify unit
                        }
                        # Merge zones
                        activity_entry.update(zones_dict)
                        
                        processed_activities.append(activity_entry)

                    except Exception as e_act:
                        logger.error(f"Error parsing activity detail: {e_act}")
                        continue
            
            # ... (Rest of function) ...

            return GarminMetrics(
                # ...
                body_battery_max=bb_max,
                body_battery_min=bb_min,
                activities=processed_activities,
                # ...
            )
