import logging
import os
import json
from datetime import date, timedelta
from src.garmin_client import GarminClient
from src.sheets_client import GoogleSheetsClient, GoogleAuthTokenRefreshError

# ---------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------
SPREADSHEET_ID = os.environ.get("SPREADSHEET_ID")
# Updated Sheet Name
SHEET_NAME = "Daily Summaries" 

# Setup Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def setup_google_credentials():
    """Creates client_secret.json from environment variable if needed."""
    if not os.path.exists('credentials'):
        os.makedirs('credentials')
    
    if not os.path.exists('credentials/client_secret.json'):
        if "GCP_SERVICE_ACCOUNT_KEY" in os.environ:
            try:
                key_dict = json.loads(os.environ["GCP_SERVICE_ACCOUNT_KEY"])
                with open('credentials/client_secret.json', 'w') as f:
                    json.dump(key_dict, f)
                logger.info("Successfully created credentials/client_secret.json from environment secret.")
            except json.JSONDecodeError:
                logger.error("GCP_SERVICE_ACCOUNT_KEY is not valid JSON.")
                raise
        else:
            logger.error("client_secret.json not found and GCP_SERVICE_ACCOUNT_KEY not set.")
            raise FileNotFoundError("Missing Google Credentials.")

async def sync():
    logger.info("Starting Garmin Sync...")
    
    # 1. Setup Google Auth
    setup_google_credentials()

    # 2. Initialize Clients
    email = os.environ["GARMIN_EMAIL"]
    password = os.environ["GARMIN_PASSWORD"]
    
    garmin_client = GarminClient(email, password)
    
    # Authenticate Garmin
    try:
        await garmin_client.authenticate()
    except Exception as e:
        logger.error(f"Authentication failed: {e}")
        return

    # Initialize Sheets Client
    try:
        sheets_client = GoogleSheetsClient(
            credentials_path='credentials/client_secret.json',
            spreadsheet_id=SPREADSHEET_ID,
            sheet_name=SHEET_NAME
        )
        logger.info(f"Connected to Spreadsheet: {SPREADSHEET_ID}")
    except Exception as e:
        logger.error(f"Failed to initialize Sheets client: {e}")
        return

    # 3. Determine Date Range
    # Set to False for daily maintenance (Last 7 days)
    # Set to True only if you need to re-download years of data
    FORCE_BACKFILL = True 

    if FORCE_BACKFILL:
        start_date = date(2023, 1, 1)
    else:
        # Look back 7 days to catch any late-syncing data (sleep/stress adjustments)
        start_date = date.today() - timedelta(days=7)
    
    end_date = date.today()
    
    logger.info(f"Syncing range: {start_date} to {end_date}")

    # 4. Loop through dates
    current_date = start_date
    metrics_buffer = []

    while current_date <= end_date:
        logger.info(f"Fetching metrics for {current_date}")
        try:
            metrics = await garmin_client.get_metrics(current_date)
            metrics_buffer.append(metrics)
        except Exception as e:
            logger.error(f"Failed to fetch data for {current_date}: {e}")
        
        current_date += timedelta(days=1)

    # 5. Upload to Google Sheets
    if metrics_buffer:
        logger.info(f"Uploading {len(metrics_buffer)} days of data to Google Sheets...")
        try:
            sheets_client.update_metrics(metrics_buffer)
            logger.info("Sync Complete!")
        except Exception as e:
            logger.error(f"Google Sheets Upload Failed: {e}")
    else:
        logger.info("No metrics found to upload.")

if __name__ == "__main__":
    import asyncio
    asyncio.run(sync())
