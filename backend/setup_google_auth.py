"""Run once locally to authorize Triage's read-only Google integrations."""

import json
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

from google_client import GOOGLE_SCOPES, TOKEN_PATH

CREDENTIALS_PATH = Path(__file__).with_name("credentials.json")


def main() -> None:
    if not CREDENTIALS_PATH.is_file():
        raise SystemExit("credentials.json is missing from the backend directory.")
    credentials_config = json.loads(CREDENTIALS_PATH.read_text(encoding="utf-8"))
    if "installed" not in credentials_config:
        raise SystemExit(
            "credentials.json must be a Google Cloud Desktop app OAuth client. "
            "Create or download an OAuth client with the Desktop app type, then retry."
        )

    flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, GOOGLE_SCOPES)
    credentials = flow.run_local_server()
    TOKEN_PATH.write_text(credentials.to_json(), encoding="utf-8")
    print(f"Google authorization saved to {TOKEN_PATH.name}.")


if __name__ == "__main__":
    main()
