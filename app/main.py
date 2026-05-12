from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi import FastAPI, UploadFile, File
import pdfplumber
import os
import json
import re
from typing import Annotated

app = FastAPI()
app.mount("/static", StaticFiles(directory="app/static"), name="static")

@app.get("/app")
def app_page():

    return FileResponse("app/static/index.html")
def root():
    return {
        "status": "vendor-agent-running"
    }


def extract_text_from_pdf(pdf_path):

    text = ""

    with pdfplumber.open(pdf_path) as pdf:

        for page in pdf.pages:

            page_text = page.extract_text()

            if page_text:
                text += page_text + "\n"

    return text


def extract_company_data(text):

    data = {}

    nit_match = re.search(r'\d{3}\d{3}\d{3}-\d', text)

    if nit_match:
        data["nit"] = nit_match.group()

    empresa_match = re.search(r'ZEHIRUT LTDA', text)

    if empresa_match:
        data["empresa"] = empresa_match.group()

    representante_match = re.search(
        r'REPRESENTANTE LEGAL\s+([A-Z\s]+)',
        text
    )

    if representante_match:
        data["representante_legal"] = representante_match.group(1)

    return data


@app.post("/upload-company-documents")
async def upload_company_documents(
    files: Annotated[
        list[UploadFile],
        File(description="Multiple PDF files")
    ]
):

    all_text = ""

    os.makedirs("storage/company_docs", exist_ok=True)

    for file in files:

        file_path = f"storage/company_docs/{file.filename}"

        with open(file_path, "wb") as f:
            f.write(await file.read())

        text = extract_text_from_pdf(file_path)

        all_text += text + "\n"

    company_data = extract_company_data(all_text)

    with open("storage/company_data.json", "w") as json_file:

        json.dump(
            company_data,
            json_file,
            indent=4
        )

    return {
        "message": "Documents processed",
        "company_data": company_data
    }