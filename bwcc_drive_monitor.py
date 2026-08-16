import os
import json
import io
import datetime
from datetime import timezone
from typing import List, Dict, Any, Optional
import requests
import google.generativeai as genai
from feedgen.feed import FeedGenerator

# Google Drive Target Folders
ROOT_FOLDER_IDS = [
    "1bxY6FSjJMrfPEGxAiq6fRhC3DGun9Ni5",
    "1Wycq7k8Wsh4bzZLociKkc_tMJmiIGsEX",
]

ARCHIVE_FILE = "bwcc_archive.json"
FEED_FILE = "bwcc_feed.xml"
FEED_TITLE = "Bearsden West Community Council"
FEED_LINK = "https://drive.google.com/drive/folders/1bxY6FSjJMrfPEGxAiq6fRhC3DGun9Ni5"
FEED_DESCRIPTION = "Automated AI-generated summaries of Bearsden West Community Council minutes, budgets, and documents."

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
DRIVE_API_KEY = os.environ.get("DRIVE_API_KEY") or GEMINI_API_KEY


def load_archive() -> Dict[str, Any]:
    if os.path.exists(ARCHIVE_FILE):
        try:
            with open(ARCHIVE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_archive(archive: Dict[str, Any]) -> None:
    with open(ARCHIVE_FILE, "w", encoding="utf-8") as f:
        json.dump(archive, f, indent=2, ensure_ascii=False)


def list_drive_folder(folder_id: str, api_key: str) -> List[Dict[str, Any]]:
    """List all immediate children in a Google Drive folder."""
    items = []
    page_token = None
    base_url = "https://www.googleapis.com/drive/v3/files"

    while True:
        params = {
            "q": f"'{folder_id}' in parents and trashed = false",
            "fields": "nextPageToken, files(id, name, mimeType, modifiedTime, webViewLink)",
            "pageSize": 100,
            "key": api_key,
        }
        if page_token:
            params["pageToken"] = page_token

        resp = requests.get(base_url, params=params)
        resp.raise_for_status()
        data = resp.json()

        items.extend(data.get("files", []))
        page_token = data.get("nextPageToken")
        if not page_token:
            break

    return items


def scan_drive_folders_recursively(folder_ids: List[str], api_key: str) -> List[Dict[str, Any]]:
    """Recursively search for all PDF files within the specified root folders."""
    discovered_pdfs = []
    folders_to_scan = list(folder_ids)
    scanned_folders = set()

    while folders_to_scan:
        current_folder = folders_to_scan.pop(0)
        if current_folder in scanned_folders:
            continue
        scanned_folders.add(current_folder)

        try:
            children = list_drive_folder(current_folder, api_key)
            for child in children:
                mime_type = child.get("mimeType", "")
                name = child.get("name", "")

                if mime_type == "application/vnd.google-apps.folder":
                    folders_to_scan.append(child["id"])
                elif mime_type == "application/pdf" or name.lower().endswith(".pdf"):
                    discovered_pdfs.append(child)
        except Exception as e:
            print(f"Error scanning folder {current_folder}: {e}")

    return discovered_pdfs


def download_drive_file(file_id: str, api_key: str) -> bytes:
    """Download binary content of a file from Google Drive."""
    url = f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media&key={api_key}"
    resp = requests.get(url)
    if resp.status_code == 200:
        return resp.content

    # Fallback to direct public export download URL
    fallback_url = f"https://drive.google.com/uc?export=download&id={file_id}"
    resp_fallback = requests.get(fallback_url)
    resp_fallback.raise_for_status()
    return resp_fallback.content


def summarize_pdf_with_gemini(pdf_bytes: bytes, filename: str) -> Dict[str, str]:
    """Process PDF content with Gemini Flash and enforce required title conventions."""
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel("gemini-2.5-flash")

    prompt = f"""
Analyze the attached Community Council PDF document ("{filename}") and provide a structured JSON response.

STRICT TITLE FORMATTING RULES:
1. If the document is meeting minutes:
   The title MUST be exactly formatted as: "Bearsden West CC Minutes - <Month YYYY>"
   Example: "Bearsden West CC Minutes - June 2025"
2. If the document is an annual or periodic budget/accounts/finance document:
   The title MUST be exactly formatted as: "Bearsden West CC Budget - <YYYY/YY>"
   Example: "Bearsden West CC Budget - 2025/26"
3. If it is another document type (e.g. agenda, constitution, newsletter):
   The title MUST be formatted as: "Bearsden West CC - <Document Type or Topic> - <Month YYYY or Date>"

SUMMARY GUIDELINES:
- Provide a detailed, high-quality, comprehensive summary formatted in clean HTML (using <h3>, <p>, <ul>, <li>, <strong>).
- Detail key discussions, decisions made, planning applications, local council updates, police reports, community issues, financial figures, and action items.

Return ONLY a valid JSON object matching this schema:
{{
  "doc_type": "minutes" | "budget" | "other",
  "title": "<Formatted Title>",
  "summary_html": "<Detailed HTML Summary>"
}}
"""

    response = model.generate_content(
        contents=[
            {"mime_type": "application/pdf", "data": pdf_bytes},
            prompt,
        ],
        generation_config={"response_mime_type": "application/json"},
    )

    result = json.loads(response.text)
    return result


def update_rss_feed(archive: Dict[str, Any]) -> None:
    """Generate or update the RSS 2.0 feed from all processed archive items."""
    fg = FeedGenerator()
    fg.title(FEED_TITLE)
    fg.link(href=FEED_LINK, rel="alternate")
    fg.description(FEED_DESCRIPTION)
    fg.language("en-gb")

    # Sort items by publication / processed date descending
    sorted_items = sorted(
        archive.values(),
        key=lambda x: x.get("processed_at", ""),
        reverse=True,
    )

    for item in sorted_items:
        fe = fg.add_entry()
        fe.id(item.get("webViewLink") or f"bwcc-{item['id']}")
        fe.title(item["title"])
        fe.link(href=item.get("webViewLink") or FEED_LINK)
        fe.description(item["summary_html"])

        if item.get("processed_at"):
            pub_date = datetime.datetime.fromisoformat(item["processed_at"])
            if pub_date.tzinfo is None:
                pub_date = pub_date.replace(tzinfo=timezone.utc)
            fe.pubDate(pub_date)

    fg.rss_file(FEED_FILE, pretty=True)


def main():
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY or GOOGLE_API_KEY environment variable is required.")

    archive = load_archive()
    print(f"Loaded {len(archive)} existing records from archive.")

    print("Scanning Google Drive folders for PDF documents...")
    all_pdfs = scan_drive_folders_recursively(ROOT_FOLDER_IDS, DRIVE_API_KEY)
    print(f"Found {len(all_pdfs)} total PDF files in target folders.")

    new_files_processed = 0

    for pdf in all_pdfs:
        file_id = pdf["id"]
        filename = pdf.get("name", "Document.pdf")

        if file_id in archive:
            continue

        print(f"Processing new PDF: {filename} (ID: {file_id})...")
        try:
            pdf_bytes = download_drive_file(file_id, DRIVE_API_KEY)
            gemini_result = summarize_pdf_with_gemini(pdf_bytes, filename)

            archive[file_id] = {
                "id": file_id,
                "name": filename,
                "title": gemini_result["title"],
                "doc_type": gemini_result.get("doc_type", "other"),
                "summary_html": gemini_result["summary_html"],
                "webViewLink": pdf.get("webViewLink", f"https://drive.google.com/file/d/{file_id}/view"),
                "modifiedTime": pdf.get("modifiedTime"),
                "processed_at": datetime.datetime.now(timezone.utc).isoformat(),
            }
            new_files_processed += 1
            print(f"Successfully summarized: {gemini_result['title']}")
        except Exception as e:
            print(f"Error processing {filename}: {e}")

    if new_files_processed > 0:
        save_archive(archive)
        update_rss_feed(archive)
        print(f"Completed. Added {new_files_processed} new summaries and updated {FEED_FILE}.")
    else:
        # Ensure RSS file exists even if no new items were added
        if not os.path.exists(FEED_FILE) and archive:
            update_rss_feed(archive)
        print("No new PDF files found. Feed is up to date.")


if __name__ == "__main__":
    main()
