# [src/main.py]

async def sync(email: str, password: str, start_date: date, end_date: date, output_type: str, profile_data: dict, profile_name: str = ""):
    # ... (existing authentication and fetching logic)

    # Filter for Stress/Activity Summary tabs (historical only)
    today = date.today()
    metrics_historical = [m for m in metrics_to_write if m.date < today]

    # === GOOGLE DRIVE (CSV) SYNC ===
    if output_type == 'drive':
        folder_id = profile_data.get('drive_folder_id')
        if not folder_id:
            logger.error(f"DRIVE_FOLDER_ID not set for {profile_name}.")
            return

        ensure_credentials_file_exists()
        
        try:
            drive_client = GoogleDriveClient('credentials/client_secret.json', folder_id)
            # Standard daily files (these can stay as metrics_to_write if you want live updates for them)
            drive_client.update_csv("garmin_sleep.csv", metrics_to_write, SLEEP_HEADERS)
            drive_client.update_csv("garmin_body_composition.csv", metrics_to_write, BODY_COMP_HEADERS)
            drive_client.update_csv("garmin_blood_pressure.csv", metrics_to_write, BP_HEADERS)
            
            # === MODIFIED LOGIC ===
            # Use metrics_historical instead of metrics_to_write so that 
            # a row is only added the day AFTER it has finished.
            if metrics_historical:
                drive_client.update_csv("general_summary.csv", metrics_historical, GENERAL_SUMMARY_HEADERS)
                drive_client.update_csv("garmin_stress.csv", metrics_historical, STRESS_HEADERS)
                drive_client.update_csv("garmin_activity_summary.csv", metrics_historical, ACTIVITY_SUMMARY_HEADERS)
            
            # Activities List (usually only processed after completion anyway)
            drive_client.update_activities_csv("garmin_activities_list.csv", metrics_to_write, ACTIVITY_HEADERS)
            logger.info(f"[{profile_name}] Google Drive CSV sync completed successfully!")
        except Exception as e:
            logger.error(f"[{profile_name}] Drive Sync Failed: {e}", exc_info=True)
            return

    # ... (rest of the function)
