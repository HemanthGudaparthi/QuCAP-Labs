"""
DB1 — Our primary research file store.

Currently implemented as a Google Drive folder (placeholder until a dedicated
database/object-store is provisioned). The interface is intentionally storage-
agnostic so it can be swapped out without touching the rest of the application.

Setup:
  1. Create a Google Cloud project and enable the Drive API.
  2. Create a Service Account and download the JSON key.
  3. Share your target Drive folder with the service account email.
  4. Set GDRIVE_CREDENTIALS_FILE and GDRIVE_FOLDER_ID in .env.
"""

import io
import json
import os
from typing import Optional


class DB1Storage:
    """Google Drive backed DB1 placeholder."""

    def __init__(self):
        self._creds_file = os.environ.get("GDRIVE_CREDENTIALS_FILE")
        self._folder_id  = os.environ.get("GDRIVE_FOLDER_ID")
        self._service    = None

        if self._creds_file and os.path.exists(self._creds_file):
            self._init_drive()

    # ── Setup ─────────────────────────────────────────────────────────────────

    def _init_drive(self):
        try:
            from google.oauth2 import service_account
            from googleapiclient.discovery import build

            creds = service_account.Credentials.from_service_account_file(
                self._creds_file,
                scopes=["https://www.googleapis.com/auth/drive"],
            )
            self._service = build("drive", "v3", credentials=creds, cache_discovery=False)
        except Exception as exc:
            print(f"[DB1Storage] Google Drive init failed ({exc}); running in stub mode.")
            self._service = None

    @property
    def available(self) -> bool:
        return self._service is not None

    # ── Core operations ───────────────────────────────────────────────────────

    def upload_research(self, research_id: str, data: dict) -> Optional[str]:
        """
        Serialize research data to JSON and upload to the DB1 Drive folder.
        Returns the Google Drive file ID, or None on failure.
        """
        if not self.available:
            return self._stub_upload(research_id, data)

        from googleapiclient.http import MediaIoBaseUpload

        content  = json.dumps(data, indent=2).encode("utf-8")
        media    = MediaIoBaseUpload(io.BytesIO(content), mimetype="application/json")
        metadata = {
            "name":    f"research_{research_id}.json",
            "parents": [self._folder_id],
        }

        try:
            f = self._service.files().create(
                body=metadata, media_body=media, fields="id"
            ).execute()
            return f.get("id")
        except Exception as exc:
            print(f"[DB1Storage] Upload failed: {exc}")
            return None

    def download_research(self, file_id: str) -> Optional[dict]:
        """Download and deserialize a research entry by Drive file ID."""
        if not self.available:
            return self._stub_download(file_id)

        from googleapiclient.http import MediaIoBaseDownload

        try:
            request    = self._service.files().get_media(fileId=file_id)
            buf        = io.BytesIO()
            downloader = MediaIoBaseDownload(buf, request)
            done       = False
            while not done:
                _, done = downloader.next_chunk()
            return json.loads(buf.getvalue().decode("utf-8"))
        except Exception as exc:
            print(f"[DB1Storage] Download failed: {exc}")
            return None

    def delete_research(self, file_id: str) -> bool:
        """Permanently delete a research file from DB1."""
        if not self.available:
            return False

        try:
            self._service.files().delete(fileId=file_id).execute()
            return True
        except Exception as exc:
            print(f"[DB1Storage] Delete failed: {exc}")
            return False

    def list_research(self) -> list[dict]:
        """List all research entries in the DB1 folder."""
        if not self.available:
            return []

        try:
            query = f"'{self._folder_id}' in parents and trashed=false"
            resp  = self._service.files().list(
                q=query, fields="files(id, name, createdTime)"
            ).execute()
            return resp.get("files", [])
        except Exception as exc:
            print(f"[DB1Storage] List failed: {exc}")
            return []

    # ── Stub mode (no credentials) ────────────────────────────────────────────

    def _stub_upload(self, research_id: str, data: dict) -> str:
        """Local JSON file fallback when Drive is unconfigured."""
        path = f"/tmp/db1_stub_{research_id}.json"
        with open(path, "w") as fh:
            json.dump(data, fh, indent=2)
        print(f"[DB1Storage] STUB: saved to {path}")
        return f"stub:{research_id}"

    def _stub_download(self, file_id: str) -> Optional[dict]:
        research_id = file_id.replace("stub:", "")
        path        = f"/tmp/db1_stub_{research_id}.json"
        try:
            with open(path) as fh:
                return json.load(fh)
        except FileNotFoundError:
            return None
