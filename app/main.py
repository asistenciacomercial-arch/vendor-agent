from openai import OpenAI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi import FastAPI, UploadFile, File
import pdfplumber
import os
import traceback
from docx import Document
from openpyxl import load_workbook

app = FastAPI()

# =========================
# GROQ CLIENT
# =========================

client = OpenAI(
    api_key=os.getenv("GROQ_API_KEY"),
    base_url="https://api.groq.com/openai/v1"
)

# =========================
# STATIC FILES
# =========================

app.mount(
    "/static",
    StaticFiles(directory="app/static"),
    name="static"
)

# =========================
# ROOT
# =========================

@app.get("/")
def root():

    return {
        "status": "vendor-agent-running"
    }

# =========================
# FRONTEND
# =========================

@app.get("/app")
def app_page():

    return FileResponse("app/static/index.html")

# =========================
# PDF TEXT EXTRACTION
# =========================

def extract_text_from_pdf(pdf_path):

    text = ""

    with pdfplumber.open(pdf_path) as pdf:

        for page in pdf.pages:

            page_text = page.extract_text()

            if page_text:
                text += page_text + "\n"

    return text

# =========================
# AI EXTRACTION
# =========================

def extract_with_ai(text):

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {
                "role": "system",
                "content": """
                Extrae información empresarial
                desde documentos legales y devuelve
                JSON limpio.

                Extrae:

                - empresa
                - nit
                - representante_legal
                - direccion
                - email
                - telefono
                - banco
                - numero_cuenta
                - tipo_cuenta
                - ciudad
                """
            },
            {
                "role": "user",
                "content": text[:12000]
            }
        ],
        temperature=0
    )

    return response.choices[0].message.content

# =========================
# UPLOAD COMPANY DOCUMENTS
# =========================

@app.post("/upload-company-documents")
async def upload_company_documents(
    files: list[UploadFile] = File(...)
):

    try:

        all_text = ""

        os.makedirs(
            "storage/company_docs",
            exist_ok=True
        )

        for file in files:

            # Solo PDFs
            if not file.filename.lower().endswith(".pdf"):
                continue

            file_path = (
                f"storage/company_docs/{file.filename}"
            )

            # Guardar archivo
            with open(file_path, "wb") as f:

                f.write(await file.read())

            # Extraer texto
            text = extract_text_from_pdf(file_path)

            # Limitar tamaño
            all_text += text[:5000] + "\n"

        # IA
        ai_response = extract_with_ai(all_text)

        with open(
            "storage/company_profile.json",
            "w",
            encoding="utf-8"
        ) as f:

            f.write(ai_response)

        return {
            "status": "success",
            "message": "Documents processed",
            "ai_response": ai_response,
            "preview_text": all_text[:3000]
        }

    except Exception as e:

        return {
            "status": "error",
            "detail": str(e),
            "trace": traceback.format_exc()
        }

@app.post("/fill-word")
async def fill_word(
    file: UploadFile = File(...)
):

    try:

        # cargar perfil empresa
        with open(
            "storage/company_profile.json",
            "r",
            encoding="utf-8"
        ) as f:

            company_data = f.read()

        # guardar word temporal
        os.makedirs(
            "storage/forms",
            exist_ok=True
        )

        form_path = (
            f"storage/forms/{file.filename}"
        )

        with open(form_path, "wb") as temp_file:

            temp_file.write(await file.read())

        # abrir word
        doc = Document(form_path)

        # recorrer párrafos
        for paragraph in doc.paragraphs:

            text = paragraph.text

            if not text.strip():
                continue

            # IA decide reemplazos
            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {
                        "role": "system",
                        "content": f"""
                        Eres un asistente que llena
                        formularios empresariales.

                        Datos empresa:

                        {company_data}

                        Si el texto contiene un campo
                        o pregunta empresarial,
                        devuelve SOLO el valor correcto.

                        Si no aplica,
                        devuelve exactamente el mismo texto.
                        """
                    },
                    {
                        "role": "user",
                        "content": text
                    }
                ],
                temperature=0
            )

            new_text = (
                response
                .choices[0]
                .message
                .content
            )

            paragraph.text = new_text

        # guardar resultado
        output_path = (
            f"storage/forms/FILLED_{file.filename}"
        )

        doc.save(output_path)

        return FileResponse(
            output_path,
            filename=f"FILLED_{file.filename}"
        )

    except Exception as e:

        return {
            "status": "error",
            "detail": str(e),
            "trace": traceback.format_exc()
        }    
@app.post("/fill-excel")
async def fill_excel(
    file: UploadFile = File(...)
):

    try:

        # cargar perfil empresa
        with open(
            "storage/company_profile.json",
            "r",
            encoding="utf-8"
        ) as f:

            company_data = f.read()

        # guardar excel
        os.makedirs(
            "storage/forms",
            exist_ok=True
        )

        excel_path = (
            f"storage/forms/{file.filename}"
        )

        with open(excel_path, "wb") as temp_file:

            temp_file.write(await file.read())

        # abrir excel
        workbook = load_workbook(excel_path)

        # recorrer hojas
        for sheet in workbook.worksheets:

            # recorrer celdas
            for row in sheet.iter_rows():

                for cell in row:

                    if cell.value is None:
                        continue

                    text = str(cell.value)

                    if len(text.strip()) == 0:
                        continue

                    # IA responde
                    response = client.chat.completions.create(
                        model="llama-3.3-70b-versatile",
                        messages=[
                            {
                                "role": "system",
                                "content": f"""
                                Eres un asistente que llena
                                formularios empresariales.

                                Datos empresa:

                                {company_data}

                                Si el texto parece un campo,
                                pregunta o etiqueta empresarial,
                                devuelve SOLO el valor correcto.

                                Si no aplica,
                                devuelve exactamente el mismo texto.
                                """
                            },
                            {
                                "role": "user",
                                "content": text
                            }
                        ],
                        temperature=0
                    )

                    new_value = (
                        response
                        .choices[0]
                        .message
                        .content
                    )

                    cell.value = new_value

        # guardar resultado
        output_path = (
            f"storage/forms/FILLED_{file.filename}"
        )

        workbook.save(output_path)

        return FileResponse(
            output_path,
            filename=f"FILLED_{file.filename}"
        )

    except Exception as e:

        return {
            "status": "error",
            "detail": str(e),
            "trace": traceback.format_exc()
        }    