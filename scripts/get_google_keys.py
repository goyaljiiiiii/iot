import os
from pathlib import Path
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build


def _load_env_file():
    env_path = Path(__file__).resolve().parents[1] / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))

_load_env_file()

# The permission scope required to manage Tasks
SCOPES = ['https://www.googleapis.com/auth/tasks']

CLIENT_ID = os.getenv("GOOGLE_TASKS_CLIENT_ID", "")
CLIENT_SECRET = os.getenv("GOOGLE_TASKS_CLIENT_SECRET", "")

if not CLIENT_ID or not CLIENT_SECRET:
    raise SystemExit("Set GOOGLE_TASKS_CLIENT_ID and GOOGLE_TASKS_CLIENT_SECRET in your .env before running this script.")

def get_everything():
    print("Opening browser for authentication...")
    
    # Set up the authentication flow
    client_config = {
        "installed": {
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }
    
    flow = InstalledAppFlow.from_client_config(client_config, scopes=SCOPES)
    creds = flow.run_local_server(port=0)

    print("\n✅ Authentication Successful! Fetching your Task Lists...\n")

    # Connect to the Google Tasks API to get the List ID
    service = build('tasks', 'v1', credentials=creds)
    results = service.tasklists().list(maxResults=10).execute()
    items = results.get('items', [])

    # Print the exact text to paste into your .env
    print("=====================================================")
    print("📋 COPY AND PASTE THIS DIRECTLY INTO YOUR .ENV FILE:")
    print("=====================================================")
    print(f"GOOGLE_TASKS_CLIENT_ID={CLIENT_ID}")
    print(f"GOOGLE_TASKS_CLIENT_SECRET={CLIENT_SECRET}")
    print(f"GOOGLE_TASKS_REFRESH_TOKEN={creds.refresh_token}")
    
    # Note: Access tokens expire after 1 hour, so usually AIs only use the refresh token
    # to get a new access token, but here it is if your setup specifically asks for it.
    print(f"GOOGLE_TASKS_ACCESS_TOKEN={creds.token}")
    
    if not items:
        print("\nNo task lists found in your Google Account.")
    else:
        # We will grab the very first task list (usually "My Tasks")
        first_list = items[0]
        print(f"GOOGLE_TASK_LIST_ID={first_list['id']}")
        print(f"GOOGLE_TASK_LIST_NAME={first_list['title']}")
        
        # If you have multiple lists, show them as options
        if len(items) > 1:
            print("\n--- Note: You have other task lists you could use instead ---")
            for item in items[1:]:
                print(f"Name: {item['title']}  -->  ID: {item['id']}")

if __name__ == '__main__':
    get_everything()