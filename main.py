from fastapi import FastAPI
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
import subprocess
import uuid
import os

app = FastAPI()

# ✅ ADD THIS CORS BLOCK
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

class CodeRequest(BaseModel):
    code: str

@app.post("/run")
async def run_code(request: CodeRequest):
    file_name = f"{uuid.uuid4()}.py"

    with open(file_name, "w") as f:
        f.write(request.code)

    try:
        result = subprocess.run(
            ["python", file_name],
            capture_output=True,
            text=True,
            timeout=5
        )
        output = result.stdout
        error = result.stderr
    except Exception as e:
        output = ""
        error = str(e)

    os.remove(file_name)

    return {"output": output, "error": error}