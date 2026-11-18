import os
import sys
from pathlib import Path
import json

# Add project root to path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from backend.core.config import settings

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube"
]

def main():
    print("=" * 60)
    print("AutoClipper: Connect YouTube Channel / Account")
    print("=" * 60)

    secrets_path = settings.BASE_DIR / settings.YOUTUBE_CLIENT_SECRETS_PATH
    token_path = settings.BASE_DIR / settings.YOUTUBE_TOKEN_PATH

    if not secrets_path.exists():
        print(f"\n[ERROR] client_secrets.json not found at: {secrets_path}")
        print("Please place your downloaded Google OAuth client secrets file there first.")
        return

    # Backup existing token if present so you never lose previous accounts
    if token_path.exists():
        backup_path = token_path.parent / "token_previous.json"
        try:
            import shutil
            shutil.copy(token_path, backup_path)
            print(f"[Notice] Previous account token backed up to: config/{backup_path.name}")
        except Exception:
            pass

    print("\n[1/3] Initiating Google OAuth Login Flow...")
    print("      A browser tab will open automatically.")
    print("      👉 Step 1: Select your Google account")
    print("      👉 Step 2: Choose your YouTube channel")
    print("      👉 Step 3: Click 'Continue' and 'Allow' on the permissions screen\n")

    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build

        flow = InstalledAppFlow.from_client_secrets_file(
            str(secrets_path),
            SCOPES
        )
        creds = flow.run_local_server(port=0, prompt='select_account consent')

        # Save credentials as the primary active token
        with open(token_path, "w") as f:
            f.write(creds.to_json())

        print("\n[2/3] Authorization successful! Verifying channel details...")
        service = build("youtube", "v3", credentials=creds)
        response = service.channels().list(part="snippet,statistics", mine=True).execute()
        items = response.get("items", [])

        if items:
            channel = items[0]
            title = channel["snippet"]["title"]
            channel_id = channel["id"]
            subscribers = channel["statistics"].get("subscriberCount", "0")

            # Also save a named copy in config/tokens/
            clean_name = "".join(c for c in title if c.isalnum() or c in (' ', '_', '-')).strip().replace(' ', '_')
            tokens_dir = token_path.parent / "tokens"
            tokens_dir.mkdir(exist_ok=True)
            named_token_path = tokens_dir / f"{clean_name}.json"
            with open(named_token_path, "w") as f:
                f.write(creds.to_json())

            print("\n" + "=" * 60)
            print(f"✅ SUCCESSFULLY CONNECTED TO YOUTUBE CHANNEL:")
            print(f"   Channel Name: {title}")
            print(f"   Channel ID:   {channel_id}")
            print(f"   Subscribers:  {subscribers}")
            print(f"   Active Token: {token_path}")
            print("=" * 60)
            print(f"\nAll set! AutoClipper is now authenticated and ready to upload.")
        else:
            print("\n[Warning] Connected to Google, but no YouTube channel was found under this account.")
            print("Please make sure you have created a YouTube channel at https://youtube.com for your account.")

    except Exception as e:
        print(f"\n[ERROR] Authentication failed: {str(e)}")

if __name__ == "__main__":
    main()
