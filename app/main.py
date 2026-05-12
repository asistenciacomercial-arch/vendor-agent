from fastapi import FastAPI, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from openai import OpenAI

from openpyxl import load_workbook
from docx import Document
from pdf2image import convert_from_path

from copy import copy

import pytesseract
import pdfplumber
import traceback
import openpyxl
import shutil
import xlrd
import json
import os

# =========================================================
# FASTAPI
# =========================================================

app = FastAPI()

app.mount(
    "/static",
    StaticFiles(directory="app/static"),
    name="static"
)

# =========================================================
# GROQ CLIENT
# =========================================================

client = OpenAI(
    api_key=os.getenv("GROQ_API_KEY"),
    base_url="https://api.groq.com/openai/v1"
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
# FIELD MAPPINGS
# =========================================================

FIELD_MAPPINGS = {

    "empresa": [
        "razón social",
        "razon social",
        "empresa",
        "nombre empresa",
        "company name"
    ],

    "nit": [
        "nit",
        "tax id",
        "identificación tributaria",
        "identificacion tributaria"
    ],

    "direccion": [
        "dirección",
        "direccion",
        "address"
    ],

    "telefono": [
        "teléfono",
        "telefono",
        "celular",
        "phone"
    ],

    "email": [
        "correo",
        "correo electrónico",
        "correo electronico",
        "email",
        "e-mail"
    ],

    "representante_legal": [
        "representante legal",
        "nombre representante",
        "legal representative"
    ],

    "banco": [
        "banco",
        "bank"
    ],

    "numero_cuenta": [
        "número de cuenta",
        "numero de cuenta",
        "account number"
    ],

    "tipo_cuenta": [
        "tipo de cuenta",
        "account type"
    ],

    "ciudad": [
        "ciudad",
        "city"
    ]
}

# =========================================================
# PDF EXTRACTION
# =========================================================

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

    # OCR fallback
    if text.strip() == "":

        try:

            images = convert_from_path(pdf_path)

            for image in images:

                ocr_text = pytesseract.image_to_string(
                    image,
                    lang="spa"
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

        model="llama-3.3-70b-versatile",

        messages=[

            {
                "role": "system",
                "content": """
                Extrae información empresarial
                desde documentos legales.

                Devuelve SOLO JSON válido.

                {
                  "empresa":"",
                  "nit":"",
                  "representante_legal":"",
                  "direccion":"",
                  "telefono":"",
                  "email":"",
                  "banco":"",
                  "numero_cuenta":"",
                  "tipo_cuenta":"",
                  "ciudad":""
                }
                """
            },

            {
                "role": "user",
                "content": text[:15000]
            }

        ],

        temperature=0
    )

    return response.choices[0].message.content

# =========================================================
# PROCESS COMPANY DOCUMENTS
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

        for file in files:

            file_path = (
                f"storage/company_docs/{file.filename}"
            )

            with open(file_path, "wb") as f:

                f.write(await file.read())

            # =====================================
            # PDF
            # =====================================

            if file.filename.lower().endswith(".pdf"):

                text = extract_text_from_pdf(file_path)

                all_text += text + "\n"

            # =====================================
            # DOCX
            # =====================================

            elif file.filename.lower().endswith(".docx"):

                doc = Document(file_path)

                for paragraph in doc.paragraphs:

                    all_text += paragraph.text + "\n"

            # =====================================
            # XLSX
            # =====================================

            elif file.filename.lower().endswith(".xlsx"):

                workbook = load_workbook(file_path)

                for sheet in workbook.worksheets:

                    for row in sheet.iter_rows():

                        for cell in row:

                            if cell.value:

                                all_text += (
                                    str(cell.value) + "\n"
                                )

            # =====================================
            # XLS
            # =====================================

            elif file.filename.lower().endswith(".xls"):

                workbook = xlrd.open_workbook(file_path)

                for sheet in workbook.sheets():

                    for row_idx in range(sheet.nrows):

                        row = sheet.row_values(row_idx)

                        for value in row:

                            if value:

                                all_text += (
                                    str(value) + "\n"
                                )

        # =====================================
        # AI
        # =====================================

        ai_response = extract_with_ai(all_text)

        try:

            cleaned = (
                ai_response
                .replace("```json", "")
                .replace("```", "")
                .strip()
            )

            company_data = json.loads(cleaned)

        except:

            company_data = {
                "raw_response": ai_response
            }

        # =====================================
        # SAVE COMPANY DATA
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
# FILL WORD
# =========================================================

@app.post("/fill-word")
async def fill_word(
    file: UploadFile = File(...)
):

    try:

        with open(
            "storage/company_data.json",
            "r",
            encoding="utf-8"
        ) as f:

            company_data = json.load(f)

        os.makedirs(
            "storage/generated",
            exist_ok=True
        )

        input_path = (
            f"storage/generated/{file.filename}"
        )

        with open(input_path, "wb") as f:

            f.write(await file.read())

        doc = Document(input_path)

        # =====================================
        # PARAGRAPHS
        # =====================================

        for paragraph in doc.paragraphs:

            text = paragraph.text.lower()

            for field, aliases in FIELD_MAPPINGS.items():

                matched = False

                for alias in aliases:

                    if alias in text:

                        matched = True
                        break

                if not matched:
                    continue

                value = company_data.get(field)

                if not value:
                    continue

                paragraph.text = (
                    paragraph.text + " " + str(value)
                )

        # =====================================
        # TABLES
        # =====================================

        for table in doc.tables:

            for row in table.rows:

                for cell in row.cells:

                    cell_text = cell.text.lower()

                    for field, aliases in FIELD_MAPPINGS.items():

                        matched = False

                        for alias in aliases:

                            if alias in cell_text:

                                matched = True
                                break

                        if not matched:
                            continue

                        value = company_data.get(field)

                        if not value:
                            continue

                        cell.text = (
                            cell.text + " " + str(value)
                        )

        output_path = (
            "storage/generated/FILLED_WORD.docx"
        )

        doc.save(output_path)

        return FileResponse(
            output_path,
            filename="FILLED_WORD.docx",
            media_type=(
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            )
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
        # VALIDATE
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

        # =====================================
        # LOAD COMPANY DATA
        # =====================================

        with open(
            "storage/company_data.json",
            "r",
            encoding="utf-8"
        ) as f:

            company_data = json.load(f)

        # =====================================
        # SAVE INPUT FILE
        # =====================================

        os.makedirs(
            "storage/generated",
            exist_ok=True
        )

        input_path = (
            f"storage/generated/{file.filename}"
        )

        with open(input_path, "wb") as f:

            f.write(await file.read())

        # =====================================
        # OPEN WORKBOOK
        # =====================================

        workbook = load_workbook(input_path)

        # =====================================
        # PROCESS SHEETS
        # =====================================

        for ws in workbook.worksheets:

            for row in ws.iter_rows():

                for cell in row:

                    if cell.value is None:
                        continue

                    cell_text = (
                        str(cell.value)
                        .strip()
                        .lower()
                    )

                    if len(cell_text) < 2:
                        continue

                    # =================================
                    # FIND MATCH
                    # =================================

                    for field, aliases in FIELD_MAPPINGS.items():

                        matched = False

                        for alias in aliases:

                            if alias in cell_text:

                                matched = True
                                break

                        if not matched:
                            continue

                        value = company_data.get(field)

                        if not value:
                            continue

                        # =============================
                        # TARGET CELL
                        # =============================

                        target_col = cell.column + 1
                        target_row = cell.row

                        target_cell = ws.cell(
                            row=target_row,
                            column=target_col
                        )

                        # =============================
                        # ONLY EMPTY CELLS
                        # =============================

                        if (
                            target_cell.value is None
                            or str(target_cell.value).strip() == ""
                        ):

                            target_cell.value = value

                            # =========================
                            # COPY STYLE
                            # =========================

                            if cell.has_style:

                                target_cell._style = (
                                    copy(cell._style)
                                )

                            if cell.font:
                                target_cell.font = (
                                    copy(cell.font)
                                )

                            if cell.fill:
                                target_cell.fill = (
                                    copy(cell.fill)
                                )

                            if cell.border:
                                target_cell.border = (
                                    copy(cell.border)
                                )

                            if cell.alignment:
                                target_cell.alignment = (
                                    copy(cell.alignment)
                                )

                            if cell.number_format:
                                target_cell.number_format = (
                                    cell.number_format
                                )

                            if cell.protection:
                                target_cell.protection = (
                                    copy(cell.protection)
                                )

        # =====================================
        # SAVE OUTPUT
        # =====================================

        output_path = (
            "storage/generated/"
            "FILLED_EXCEL.xlsx"
        )

        workbook.save(output_path)

        extension = os.path.splitext(file.filename)[1]

        output_path = f"storage/FILLED_EXCEL{extension}"

        if extension == ".xlsx":

            workbook.save(output_path)

        elif extension == ".xls":

            workbook.save(output_path)

        return FileResponse(
            output_path,
            filename=f"FILLED_EXCEL{extension}"
        )

    except Exception as e:

        return {

            "status": "error",

            "detail": str(e),

            "trace": traceback.format_exc()
        }