from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import io
from PyPDF2 import PdfReader
from langchain.text_splitter import RecursiveCharacterTextSplitter


# CONFIG

SERVICE_ACCOUNT_FILE = r"C:\EDU\edugen\config\drive_credentials.json"
FOLDER_ID = "13M1b5cDEVanQsRM5kNlq75cW1bVRRPxM"  # your shared folder ID
SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]


# AUTHENTICATE

credentials = service_account.Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE, scopes=SCOPES
)
service = build("drive", "v3", credentials=credentials)


# LIST ALL PDFs IN FOLDER

def list_pdfs(folder_id):
    query = f"'{folder_id}' in parents and mimeType='application/pdf'"
    results = service.files().list(
        q=query, pageSize=1000, fields="files(id, name)"
    ).execute()
    return results.get("files", [])


# READ PDF CONTENT

def read_pdf(file_id):
    request = service.files().get_media(fileId=file_id)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)

    done = False
    while not done:
        status, done = downloader.next_chunk()

    fh.seek(0)
    reader = PdfReader(fh)
    text = ""
    for page in reader.pages:
        text += page.extract_text() + "\n"
    return text


# CHUNK PDF TEXT

def chunk_text(text, chunk_size=1000, chunk_overlap=150):
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size, chunk_overlap=chunk_overlap
    )
    return splitter.split_text(text)


# MAIN EXECUTION

if __name__ == "__main__":
    pdfs = list_pdfs(FOLDER_ID)
    print(f"Found {len(pdfs)} PDFs in folder")

    all_chunks = []
    for pdf in pdfs[:5]:  # first 5 PDFs for testing
        print(f"Reading {pdf['name']} ...")
        content = read_pdf(pdf["id"])
        chunks = chunk_text(content)
        print(f"Generated {len(chunks)} chunks")
        all_chunks.extend(chunks)

    print(f"Total chunks from first 5 PDFs: {len(all_chunks)}")
    print("Sample chunk:\n", all_chunks[0][:500])