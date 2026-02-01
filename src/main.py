import logging
import asyncio
import os
import sys
from datetime import date, datetime, timedelta # <--- FIXED: Added missing imports
from typing import List, Optional
import typer
from dotenv import load_dotenv

from src.garmin_client import GarminClient
from src.drive_client import GoogleDriveClient
from src.sheets_client import GoogleSheetsClient
from src.config import (
    HEADERS, GENERAL_SUMMARY_HEADERS, SLEEP_HEADERS, BODY_COMP_HEADERS,
    STRESS_HEADERS, BP_HEADERS, ACTIVITY_SUMMARY_HEADERS, ACTIVITY_HEADERS
)

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

app = typer.Typer()

async def sync(email: str, password: str, start_date: date, end_date: date, output_type: str, profile_data: dict, profile_name: str = ""):
    """
    Main sync logic: Authenticates, fetches data, and writes to Drive or Sheets.
    """
    try:
        # 1. Authenticate
        client = GarminClient(email, password, profile_name)
        await client.authenticate()

        # 2. Fetch Metrics Loop
        metrics_to_write = []
        current_date = start_date
        while current_date <= end_date:
            logger.info(f"Fetching metrics for {current_date}")
            m = await client.get_metrics(current_date)
            if m:
                metrics_to_write.append(m)
            current_date += timedelta(days=1)

        # 3. Filter for Historical Data Only
        today = date.today()
        # This list excludes any data from today.
        metrics_historical = [m for m in metrics_to_write if m.date < today]

        # 4. Export Data
        # === GOOGLE DRIVE (CSV) SYNC ===
        if output_type == 'drive':
            folder_id = profile_data.get('drive_folder_id')
            if not folder_id:
                logger.error(f"DRIVE_FOLDER_ID not set for {profile_name}.")
                return

            try:
                drive_client = GoogleDriveClient('credentials/client_secret.json', folder_id)
                
                # A. LIVE FILES (Update with 'metrics_to_write' to include today's data)
                drive_client.update_csv("garmin_sleep.csv", metrics_to_write, SLEEP_HEADERS)
                drive_client.update_csv("garmin_body_composition.csv", metrics_to_write, BODY_COMP_HEADERS)
                drive_client.update_csv("garmin_blood_pressure.csv", metrics_to_write, BP_HEADERS)
                drive_client.update_activities_csv("garmin_activities_list.csv", metrics_to_write, ACTIVITY_HEADERS)
                
                # B. HISTORICAL ONLY FILES (Update with 'metrics_historical')
                if metrics_historical:
                    # STRICTLY HISTORICAL: This file will NOT contain today's data.
                    drive_client.update_csv("general_summary.csv", metrics_historical, GENERAL_SUMMARY_HEADERS)
                    
                    # These are typically historical too, as stress/daily summary is best calculated end-of-day
                    drive_client.update_csv("garmin_stress.csv", metrics_historical, STRESS_HEADERS)
                    drive_client.update_csv("garmin_activity_summary.csv", metrics_historical, ACTIVITY_SUMMARY_HEADERS)
                
                logger.info(f"[{profile_name}] Google Drive CSV sync completed successfully!")
            except Exception as e:
                logger.error(f"[{profile_name}] Drive Sync Failed: {e}", exc_info=True)
                return

        # === GOOGLE SHEETS SYNC ===
        elif output_type == 'sheets':
            sheet_id = profile_data.get('sheet_id')
            if not sheet_id:
                logger.error(f"SHEET_ID not set for {profile_name}.")
                return
            
            try:
                sheets_client = GoogleSheetsClient('credentials/client_secret.json', sheet_id, profile_data.get('sheet_name', 'Garmin Data'))
                # Update Sheets
                sheets_client.update_metrics(metrics_to_write)
                sheets_client.update_activities_tab(metrics_to_write)
                sheets_client.sort_sheets()
                logger.info(f"[{profile_name}] Google Sheets sync completed successfully!")
            except Exception as e:
                 logger.error(f"[{profile_name}] Sheets Sync Failed: {e}", exc_info=True)

    except Exception as e:
        logger.error(f"[{profile_name}] Sync process failed: {e}", exc_info=True)


@app.command()
def cli_sync(
    start_date: str = typer.Option(..., help="Start date YYYY-MM-DD"),
    end_date: str = typer.Option(..., help="End date YYYY-MM-DD"),
    profile: str = typer.Option("USER1", help="Profile section in .env (USER1, USER2)"),
    output_type: str = typer.Option("drive", help="Output type: drive or sheets")
):
    """
    Command line interface for automated syncs.
    """
    # Load profile data
    email = os.getenv(f"{profile}_GARMIN_EMAIL")
    password = os.getenv(f"{profile}_GARMIN_PASSWORD")
    
    profile_data = {
        'drive_folder_id': os.getenv(f"{profile}_DRIVE_FOLDER_ID"),
        'sheet_id': os.getenv(f"{profile}_SHEET_ID"),
        'sheet_name': os.getenv(f"{profile}_SHEET_NAME"),
        'user_name': os.getenv(f"{profile}_NAME"),
        'user_dob': os.getenv(f"{profile}_DOB"),
        'user_gender': os.getenv(f"{profile}_GENDER")
    }

    if not email or not password:
        logger.error(f"Credentials not found for {profile}")
        return

    try:
        s_date = datetime.strptime(start_date, "%Y-%m-%d").date()
        e_date = datetime.strptime(end_date, "%Y-%m-%d").date()
        
        asyncio.run(sync(email, password, s_date, e_date, output_type, profile_data, profile))
    except ValueError:
        logger.error("Invalid date format. Use YYYY-MM-DD")

def interactive():
    """
    Simple interactive menu if no arguments provided.
    """
    print("Welcome to GarminGo!")
    print("1. CSV (Drive)")
    print("2. Google Sheets")
    choice = input("Select output (1/2): ")
    output_type = 'drive' if choice == '1' else 'sheets'
    
    # Simple profile selector (defaults to USER1 for simplicity in this example)
    profile = "USER1" 
    
    start_str = input("Enter start date (YYYY-MM-DD): ")
    end_str = input("Enter end date (YYYY-MM-DD): ")
    
    cli_sync(start_str, end_str, profile, output_type)

def main():
    if len(sys.argv) > 1:
        app()
    else:
        interactive()

if __name__ == "__main__":
    main()
