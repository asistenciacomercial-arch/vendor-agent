from openai import OpenAI
from pdf2image import convert_from_path
import pytesseract
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi import FastAPI, UploadFile, File
import pdfplumber
import os
import json
import re
from typing import Annotated

app = FastAPI()
client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY")
)
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

    try:

        with pdfplumber.open(pdf_path) as pdf:

            for page in pdf.pages:

                page_text = page.extract_text()

                if page_text:
                    text += page_text + "\n"

    except:
        pass

    if text.strip() == "":

        images = convert_from_path(pdf_path)

        for image in images:

            ocr_text = pytesseract.image_to_string(
                image,
                lang="eng"
            )

            text += ocr_text + "\n"

    return text

def extract_with_ai(text):

    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {
                "role": "system",
                "content": """
                Extrae información empresarial
                de documentos legales y devuelve
                JSON limpio.

                Extrae:
                - empresa
                - nit
                - representante legal
                - email
                - teléfono
                - dirección
                - banco
                - numero_cuenta
                """
            },
            {
                "role": "user",
                "content": text[:15000]
            }
        ]
    )

    return response.choices[0].message.content

def extract_company_data(text):

    data = {}

    nit_match = re.search(
        r'(\d{3}[.,]?\d{3}[.,]?\d{3}-?\d)',
        text
    )

    if nit_match:
        data["nit"] = nit_match.group()

    email_match = re.search(
        r'[\w\.-]+@[\w\.-]+\.\w+',
        text
    )

    if email_match:
        data["email"] = email_match.group()

    empresa_match = re.search(
        r'([A-Z\s]+(?:LTDA|SAS|SA|S\.A\.S\.|LIMITADA))',
        text
    )
    phone_match = re.search(
        r'(\+57\s?\d{10}|\d{7,10})',
        text
    )

    if phone_match:
        data["telefono"] = phone_match.group()
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
    files: list[UploadFile] = File(...)
):

    try:

        all_text = ""

        os.makedirs("storage/company_docs", exist_ok=True)

        for file in files:

            file_path = f"storage/company_docs/{file.filename}"

            with open(file_path, "wb") as f:
                f.write(await file.read())

            text = extract_text_from_pdf(file_path)

            all_text += text + "\n"

        ai_response = extract_with_ai(all_text)

        return {
            "message": "Documents processed",
            "ai_response": ai_response
        }

    except Exception as e:

        return {
            "status": "error",
            "detail": str(e)
        }