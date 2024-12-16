import os
import io
import shutil
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import google.auth.exceptions
import pickle
import sys
import hashlib

# Nastavte ID složky na Google Drive (složka, která obsahuje XLSX soubory)
FOLDER_ID = "1rYVDD6gpYTxKBg28AKl8gaeClDx5Ag1Q"  # <- sem vložte ID složky z Google Drive

# Příprava cest
update_app_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.abspath(os.path.join(update_app_dir, ".."))
timetables_dir = os.path.join(root_dir, "Jízdní řády")

# Pokud neexistuje složka, vytvoříme ji
if not os.path.exists(timetables_dir):
    os.makedirs(timetables_dir)

# Rozsah pro Google Drive API - přístup k souborům
SCOPES = ['https://www.googleapis.com/auth/drive.readonly']

def get_credentials():
    creds = None
    token_path = os.path.join(update_app_dir, 'token.json')
    creds_path = os.path.join(update_app_dir, 'credentials.json')

    if not os.path.exists(creds_path):
        print("Soubor credentials.json nebyl nalezen. Nahrajte ho do složky update_app.")
        sys.exit(1)

    # Pokud už máme uložený token, načteme ho
    if os.path.exists(token_path):
        with open(token_path, 'rb') as token:
            creds = pickle.load(token)

    # Pokud nemáme platné přihlašovací údaje, požádáme o ně
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except google.auth.exceptions.RefreshError:
                # Pokud refresh selže, musíme znovu projít ověřovacím procesem
                creds = None
        else:
            flow = InstalledAppFlow.from_client_secrets_file(creds_path, SCOPES)
            creds = flow.run_local_server(port=0)

        # Uložíme token pro příští použití
        with open(token_path, 'wb') as token:
            pickle.dump(creds, token)

    return creds

def get_drive_service():
    creds = get_credentials()
    service = build('drive', 'v3', credentials=creds)
    return service

def get_remote_files(service):
    # Získání seznamu XLSX souborů ze složky FOLDER_ID
    query = f"'{FOLDER_ID}' in parents and mimeType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' and trashed=false"
    files = []
    page_token = None
    while True:
        response = service.files().list(
            q=query,
            spaces='drive',
            fields='nextPageToken, files(id, name, md5Checksum)',
            pageToken=page_token
        ).execute()

        for file in response.get('files', []):
            files.append(file)

        page_token = response.get('nextPageToken', None)
        if page_token is None:
            break
    return files

def md5_of_file(path):
    # Vrátí MD5 hash lokálního souboru
    hasher = hashlib.md5()
    with open(path, 'rb') as f:
        buf = f.read()
        hasher.update(buf)
    return hasher.hexdigest()

def sync_files(service):
    print("Zjišťuji soubory na Google Drive...")
    remote_files = get_remote_files(service)
    remote_map = {f['name']: f for f in remote_files}

    # Lokální soubory (XLSX)
    local_files = [f for f in os.listdir(timetables_dir) if f.endswith('.xlsx') and not f.startswith('~$')]
    local_map = {f: os.path.join(timetables_dir, f) for f in local_files}

    # Odstranit lokální soubory, které už nejsou na GDrive
    for local_file in local_files:
        if local_file not in remote_map:
            print(f"Lokální soubor {local_file} již není na GDrive - mažu...")
            os.remove(local_map[local_file])

    # Stáhnout nebo aktualizovat soubory z GDrive
    for rfile in remote_files:
        name = rfile['name']
        file_id = rfile['id']
        remote_md5 = rfile.get('md5Checksum')

        local_path = os.path.join(timetables_dir, name)

        need_download = False
        if not os.path.exists(local_path):
            # Soubor lokálně neexistuje, stáhneme ho
            print(f"Stahuji nový soubor: {name}")
            need_download = True
        else:
            # Soubor již existuje, porovnáme MD5
            local_md5 = md5_of_file(local_path)
            if local_md5 != remote_md5:
                print(f"Soubor {name} se změnil na GDrive, stahuji novou verzi...")
                need_download = True

        if need_download:
            request = service.files().get_media(fileId=file_id)
            fh = io.BytesIO()
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                status, done = downloader.next_chunk()

            # Zapsat stažená data na disk
            fh.seek(0)
            with open(local_path, 'wb') as f:
                shutil.copyfileobj(fh, f)
            print(f"Soubor {name} byl úspěšně stažen.")

def main():
    print("Aktualizace dat z Google Drive...")
    print(f"Data se ukládají do: {timetables_dir}")
    service = get_drive_service()

    sync_files(service)

    print("Aktualizace dokončena.")

if __name__ == "__main__":
    main()
