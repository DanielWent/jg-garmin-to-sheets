import os, sys, csv, logging, re, asyncio, json
from datetime import datetime, date, timedelta
from pathlib import Path
import typer
from dotenv import load_dotenv, find_dotenv
from src.garmin_client import GarminClient
from src.drive_client import GoogleDriveClient
from src.config import GENERAL_SUMMARY_HEADERS, GarminMetrics, SLEEP_HEADERS, BODY_COMP_HEADERS, BP_HEADERS, STRESS_HEADERS

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
app = typer.Typer()

async def sync(email, password, start_date, end_date, output_type, profile_data, profile_name=""):
    try:
        client = GarminClient(email, password, profile_name=profile_name, manual_name=profile_data.get('manual_name'), manual_dob=profile_data.get('manual_dob'), manual_gender=profile_data.get('manual_gender'))
        await client.authenticate()
    except Exception as e: logger.error(f"Auth failed: {e}"); return

    metrics = []
    curr = start_date
    # Fields requiring NA/PENDING logic (removed stress durations, added new metrics)
    fields_to_validate = ['average_stress', 'steps', 'floors_climbed', 'total_calories', 'intensity_minutes', 'body_battery_min', 'active_calories', 'body_battery_charged', 'body_battery_drain', 'training_readiness']

    while curr <= end_date:
        logger.info(f"[{profile_name}] Fetching {curr.isoformat()}")
        day = await client.get_metrics(curr)
        if curr >= date.today():
            for f in fields_to_validate: setattr(day, f, "PENDING")
        else:
            for f in fields_to_validate:
                if getattr(day, f) is None: setattr(day, f, "NA")
        metrics.append(day); curr += timedelta(days=1)

    if output_type == 'drive':
        drive = GoogleDriveClient('credentials/client_secret.json', profile_data['drive_folder_id'])
        prefix = "drw_" if profile_name == "USER1" else "aflw_"
        drive.update_csv(f"{prefix}garmin_data.csv", metrics, GENERAL_SUMMARY_HEADERS)
        drive.update_csv(f"{prefix}garmin_sleep.csv", metrics, SLEEP_HEADERS)
        drive.update_csv(f"{prefix}garmin_stress.csv", [m for m in metrics if m.date < date.today()], STRESS_HEADERS)
        logger.info(f"[{profile_name}] Sync complete.")

# ... [Include your existing load_user_profiles and CLI entry logic here] ...
