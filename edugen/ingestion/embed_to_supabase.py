from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import io
from PyPDF2 import PdfReader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from supabase import create_client, Client
import os


# CONFIG

SERVICE_ACCOUNT_FILE = r"C:\EDU\edugen\config\drive_credentials.json"
FOLDER_ID = "13M1b5cDEVanQsRM5kNlq75cW1bVRRPxM"  # your shared folder ID
SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]

SUPABASE_URL = "https://jwuxmjwgeqwvryupluod.supabase.co"
SUPABASE_KEY = "sb_secret_aTmKc4oVYuHOGsqRwO4HbQ_2yKZtIUs"

# Initialize Supabase client
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Initialize embeddings
embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")


# AUTHENTICATE GOOGLE DRIVE

credentials = service_account.Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE, scopes=SCOPES
)
service = build("drive", "v3", credentials=credentials)


# HELPERS

def list_pdfs(folder_id):
    query = f"'{folder_id}' in parents and mimeType='application/pdf'"
    results = service.files().list(
        q=query, pageSize=1000, fields="files(id, name)"
    ).execute()
    return results.get("files", [])

def read_pdf(file_id):
    request = service.files().get_media(fileId=file_id)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    fh.seek(0)
    reader = PdfReader(fh)
    text = ""
    for page in reader.pages:
        page_text = page.extract_text()
        if page_text:
            text += page_text + "\n"
    return text

def chunk_text(text, chunk_size=1000, chunk_overlap=150):
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size, chunk_overlap=chunk_overlap
    )
    return splitter.split_text(text)

def already_uploaded(pdf_name):
    """Check if this PDF has already been processed in Supabase"""
    result = supabase.table("pdf_chunks").select("pdf_name").eq("pdf_name", pdf_name).execute()
    return len(result.data) > 0


# MAIN EXECUTION

if __name__ == "__main__":
    pdfs = list_pdfs(FOLDER_ID)
    print(f"Found {len(pdfs)} PDFs in Drive folder")

    total_chunks = 0

    for pdf in pdfs:
        if already_uploaded(pdf["name"]):
            print(f"Skipping {pdf['name']} (already uploaded)")
            continue

        print(f"\nProcessing PDF: {pdf['name']}")
        content = read_pdf(pdf["id"])
        raw_chunks = chunk_text(content)
        print(f"Generated {len(raw_chunks)} chunks for {pdf['name']}")
        total_chunks += len(raw_chunks)

        structured_chunks = [
            {
                "pdf_name": pdf["name"],
                "chunk_index": i,
                "content": chunk_text
            }
            for i, chunk_text in enumerate(raw_chunks)
        ]

        for chunk in structured_chunks:
            vector = embeddings.embed_documents([chunk["content"]])[0]
            # Ensure numeric storage
            vector = [float(x) for x in vector]

            data = {
                "pdf_name": chunk["pdf_name"],
                "chunk_index": chunk["chunk_index"],
                "content": chunk["content"],
                "embedding": vector
            }
            # UPSERT to avoid duplicates (requires UNIQUE constraint on pdf_name + chunk_index)
            supabase.table("pdf_chunks").upsert(
                data, on_conflict=["pdf_name", "chunk_index"]
            ).execute()

        print(f"Inserted all chunks of {pdf['name']} into Supabase")

    print(f"\nAll PDFs processed. Total chunks inserted: {total_chunks}")