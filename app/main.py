from openai import OpenAI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi import FastAPI, UploadFile, File
import pdfplumber
import os
import traceback

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