from openai import OpenAI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi import FastAPI, UploadFile, File
import pdfplumber
import os
import traceback

app = FastAPI()

client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY")
)

app.mount(
    "/static",
    StaticFiles(directory="app/static"),
    name="static"
)


@app.get("/")
def root():

    return {
        "status": "vendor-agent-running"
    }


@app.get("/app")
def app_page():

    return FileResponse("app/static/index.html")


def extract_text_from_pdf(pdf_path):

    text = ""

    with pdfplumber.open(pdf_path) as pdf:

        for page in pdf.pages:

            page_text = page.extract_text()

            if page_text:
                text += page_text + "\n"

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
                - representante_legal
                - direccion
                - email
                - telefono
                - banco
                - numero_cuenta
                - tipo_cuenta
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

            file_path = (
                f"storage/company_docs/{file.filename}"
            )

            with open(file_path, "wb") as f:

                f.write(await file.read())

            text = extract_text_from_pdf(file_path)

            all_text += text + "\n"

        ai_response = extract_with_ai(all_text)

        return {
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