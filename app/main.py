from fastapi import FastAPI, UploadFile, File
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from openpyxl import load_workbook
from docx import Document
from pdf2image import convert_from_path

from openai import OpenAI

import pytesseract
import pdfplumber
import shutil
import traceback
import tempfile
import uuid
import json
import re
import os

# =========================================================
# APP
# =========================================================

app = FastAPI()

app.mount(
    "/static",
    StaticFiles(directory="app/static"),
    name="static"
)

# =========================================================
# OPENAI
# =========================================================

client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY")
)

# =========================================================
# ROOT
# =========================================================

@app.get("/")
def root():

    return {
        "status": "vendor-agent-running"
    }

# =========================================================
# FRONTEND
# =========================================================

@app.get("/app")
def app_page():

    return FileResponse("app/static/index.html")

# =========================================================
# PDF TEXT EXTRACTION
# =========================================================

def extract_text_from_pdf(pdf_path):

    text = ""

    # ==========================
    # NORMAL PDF EXTRACTION
    # ==========================

    try:

        with pdfplumber.open(pdf_path) as pdf:

            for page in pdf.pages:

                page_text = page.extract_text()

                if page_text:
                    text += page_text + "\n"

    except:
        pass

    # ==========================
    # OCR FALLBACK
    # ==========================

    if text.strip() == "":

        try:

            images = convert_from_path(pdf_path)

            for image in images:

                ocr_text = pytesseract.image_to_string(
                    image,
                    lang="eng"
                )

                text += ocr_text + "\n"

        except:
            pass

    return text

# =========================================================
# AI EXTRACTION
# =========================================================

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
                - representante_legal
                - email
                - telefono
                - direccion
                - banco
                - numero_cuenta
                - tipo_cuenta
                - ciudad

                Devuelve SOLO JSON válido.
                """
            },

            {
                "role": "user",
                "content": text[:15000]
            }

        ]
    )

    return response.choices[0].message.content

# =========================================================
# SAFE JSON PARSER
# =========================================================

def parse_ai_json(ai_response):

    try:

        cleaned = ai_response.strip()

        cleaned = cleaned.replace("```json", "")
        cleaned = cleaned.replace("```", "")

        return json.loads(cleaned)

    except:

        return {}

# =========================================================
# DOCUMENT PROCESSING
# =========================================================

@app.post("/upload-company-documents")
async def upload_company_documents(
    files: list[UploadFile] = File(...)
):

    try:

        os.makedirs(
            "storage/company_docs",
            exist_ok=True
        )

        all_text = ""

        # =====================================
        # SAVE + READ FILES
        # =====================================

        for file in files:

            file_path = (
                f"storage/company_docs/{file.filename}"
            )

            with open(file_path, "wb") as f:

                f.write(await file.read())

            # ==========================
            # PDF
            # ==========================

            if file.filename.lower().endswith(".pdf"):

                text = extract_text_from_pdf(file_path)

                all_text += text + "\n"

        # =====================================
        # AI EXTRACTION
        # =====================================

        ai_response = extract_with_ai(all_text)

        company_data = parse_ai_json(ai_response)

        # =====================================
        # SAVE PROFILE
        # =====================================

        os.makedirs(
            "storage",
            exist_ok=True
        )

        with open(
            "storage/company_data.json",
            "w",
            encoding="utf-8"
        ) as f:

            json.dump(
                company_data,
                f,
                indent=4,
                ensure_ascii=False
            )

        return {

            "status": "success",

            "message": "Documents processed",

            "company_data": company_data,

            "preview_text": all_text[:3000]
        }

    except Exception as e:

        return {

            "status": "error",

            "detail": str(e),

            "trace": traceback.format_exc()
        }

# =========================================================
# LOAD COMPANY DATA
# =========================================================

def load_company_data():

    try:

        with open(
            "storage/company_data.json",
            "r",
            encoding="utf-8"
        ) as f:

            return json.load(f)

    except:

        return {}

# =========================================================
# FILL WORD
# =========================================================

@app.post("/fill-word")
async def fill_word(
    file: UploadFile = File(...)
):

    try:

        company_data = load_company_data()

        os.makedirs(
            "storage/temp",
            exist_ok=True
        )

        input_path = (
            f"storage/temp/{uuid.uuid4()}.docx"
        )

        with open(input_path, "wb") as f:

            shutil.copyfileobj(file.file, f)

        # =====================================
        # OPEN WORD
        # =====================================

        doc = Document(input_path)

        # =====================================
        # PARAGRAPHS
        # =====================================

        for paragraph in doc.paragraphs:

            for key, value in company_data.items():

                if value is None:
                    continue

                if key.lower() in paragraph.text.lower():

                    paragraph.text = (
                        f"{paragraph.text} {value}"
                    )

        # =====================================
        # TABLES
        # =====================================

        for table in doc.tables:

            for row in table.rows:

                for cell in row.cells:

                    for key, value in company_data.items():

                        if value is None:
                            continue

                        if key.lower() in cell.text.lower():

                            cell.text = (
                                f"{cell.text} {value}"
                            )

        # =====================================
        # SAVE
        # =====================================

        output_path = (
            f"storage/temp/FILLED_{uuid.uuid4()}.docx"
        )

        doc.save(output_path)

        return FileResponse(

            output_path,

            media_type=(
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            ),

            filename="FILLED_WORD.docx"
        )

    except Exception as e:

        return {

            "status": "error",

            "detail": str(e),

            "trace": traceback.format_exc()
        }

# =========================================================
# FILL EXCEL
# =========================================================

@app.post("/fill-excel")
async def fill_excel(
    file: UploadFile = File(...)
):

    try:

        # =====================================
        # VALIDATE FORMAT
        # =====================================

        valid_extensions = (
            ".xlsx",
            ".xlsm"
        )

        if not file.filename.lower().endswith(valid_extensions):

            return {
                "status": "error",
                "detail": (
                    "Formato no soportado. "
                    "Use .xlsx o .xlsm"
                )
            }

        company_data = load_company_data()

        os.makedirs(
            "storage/temp",
            exist_ok=True
        )

        input_path = (
            f"storage/temp/{uuid.uuid4()}.xlsx"
        )

        with open(input_path, "wb") as f:

            shutil.copyfileobj(file.file, f)

        # =====================================
        # OPEN EXCEL
        # =====================================

        wb = load_workbook(input_path)

        # =====================================
        # PROCESS SHEETS
        # =====================================

        for ws in wb.worksheets:

            for row in ws.iter_rows():

                for cell in row:

                    if cell.value is None:
                        continue

                    cell_text = str(cell.value).lower()

                    for key, value in company_data.items():

                        if value is None:
                            continue

                        if key.lower() in cell_text:

                            # =====================
                            # WRITE NEXT CELL
                            # =====================

                            target_col = cell.column + 1
                            target_row = cell.row

                            ws.cell(
                                row=target_row,
                                column=target_col
                            ).value = value

        # =====================================
        # SAVE
        # =====================================

        output_path = (
            f"storage/temp/FILLED_{uuid.uuid4()}.xlsx"
        )

        wb.save(output_path)

        # =====================================
        # RETURN FILE
        # =====================================

        return FileResponse(

            output_path,

            media_type=(
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ),

            filename="FILLED_EXCEL.xlsx"
        )

    except Exception as e:

        return {

            "status": "error",

            "detail": str(e),

            "trace": traceback.format_exc()
        }