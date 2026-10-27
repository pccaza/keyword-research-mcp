"""One-time helper: obtain a Google Ads OAuth refresh token."""

import os
import sys
from getpass import getpass
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/adwords"]


def read_env_file(path=Path(".env")):
    values = {}
    if path.exists():
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")
    return values


file_values = read_env_file()
client_id = (
    os.environ.get("GOOGLE_ADS_CLIENT_ID")
    or file_values.get("GOOGLE_ADS_CLIENT_ID")
    or input("Client ID: ").strip()
)
client_secret = (
    os.environ.get("GOOGLE_ADS_CLIENT_SECRET")
    or file_values.get("GOOGLE_ADS_CLIENT_SECRET")
    or getpass("Client secret (hidden): ").strip()
)

if not client_id or not client_secret:
    sys.exit("Both a client ID and client secret are required.")

flow = InstalledAppFlow.from_client_config(
    {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }
    },
    scopes=SCOPES,
)

print("\nA browser window will open. Sign in with the Google account that has")
print("access to your Google Ads account, then approve the request.\n")

port = int(os.environ.get("OAUTH_PORT", "0"))
if port:
    print(f"Using fixed port {port}. The OAuth client must register exactly:")
    print(f"    http://localhost:{port}/\n")

credentials = flow.run_local_server(port=port, access_type="offline", prompt="consent")

if not credentials.refresh_token:
    sys.exit(
        "No refresh token returned. Revoke prior access for this client at\n"
        "https://myaccount.google.com/permissions and run this again."
    )

print("\n" + "=" * 60)
print("Add this line to your .env file:\n")
print(f"GOOGLE_ADS_REFRESH_TOKEN={credentials.refresh_token}")
print("=" * 60)
