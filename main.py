from fastapi import FastAPI, Request
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import subprocess
import uuid
import os
import glob
import re
import sys

# --- CONFIGURATION & LIMITER ---
limiter = Limiter(key_func=get_remote_address)
app = FastAPI()
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ✅ CORS: Allows your Vercel frontend to talk to this Render backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Supported languages mapping
LANG_CONFIG = {
    "python": {"extension": "py", "command": "python"},
    "javascript": {"extension": "js", "command": "node"}
}

class CodeRequest(BaseModel):
    code: str
    language: str

@app.get("/versions")
async def get_versions():
    try:
        # Get Python version
        py_ver = f"{sys.version_info.major}.{sys.version_info.minor}"
        
        # Get Node version
        # Added shell=True for better local compatibility on Windows
        node_result = subprocess.run(
            ["node", "-v"], 
            capture_output=True, 
            text=True,
            shell=True 
        )
        node_ver = node_result.stdout.strip().replace('v', '')
        
        return {
            "python": py_ver,
            "javascript": node_ver
        }
    except Exception:
        # Fallback if node isn't found
        return {"python": "3.x", "javascript": "20.x"}

# --- STARTUP CLEANUP ---
@app.on_event("startup")
async def startup_event():
    """Wipes any orphan files left from previous crashes on startup."""
    patterns = ["*.py", "*.js"]
    for pattern in patterns:
        for f in glob.glob(pattern):
            try:
                # Only delete UUID-style filenames to avoid deleting main scripts
                if len(f) > 30: 
                    os.remove(f)
                    print(f"Cleanup on startup: Removed {f}")
            except Exception as e:
                print(f"Startup cleanup error: {e}")

# --- MAIN RUN ENDPOINT ---
@app.post("/run")
@limiter.limit("10/minute") # Protects your server from abuse
async def run_code(request: Request, code_req: CodeRequest):
    lang = code_req.language.lower()
    
    if lang not in LANG_CONFIG:
        return {"output": f"Error: Language '{lang}' is not supported."}

    config = LANG_CONFIG[lang]
    # Generate a unique filename to prevent collision between users
    file_name = f"{uuid.uuid4()}.{config['extension']}"
    file_path = os.path.abspath(file_name)

    try:
        # Write the user's code to a temporary file
        with open(file_path, "w") as f:
            f.write(code_req.code)

        # Execute code with a strict 5-second timeout
        result = subprocess.run(
            [config["command"], file_path],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        # Determine output: if returncode is 0, it's a success
        if result.returncode == 0:
            return {"output": result.stdout}
        else:
            raw_error = result.stderr
            # This regex looks for your UUID filename and removes it
            clean_error = re.sub(rf".*{re.escape(file_name)}:?", "Line ", raw_error)
            return {"output": f"Execution Error:\n{clean_error.strip()}"}

    except subprocess.TimeoutExpired:
        return {"output": "Error: Execution timed out (5s limit). Check for infinite loops."}
    except Exception as e:
        return {"output": f"System Error: {str(e)}"}
    
    finally:
        # ✅ THE CLEANER: Always deletes the file immediately after execution
       if os.path.exists(file_path):
            # Only delete if the filename is a UUID (very long) 
            # and definitely not our script name
            if len(file_name) > 20 and file_name != "main.py":
                try:
                    os.remove(file_path)
                except Exception as cleanup_error:
                    print(f"Cleanup failed: {cleanup_error}")

@app.get("/")
async def root():
    return {"status": "Deepak IDE Backend is Online"}