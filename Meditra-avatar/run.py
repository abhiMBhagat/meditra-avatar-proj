#!/usr/bin/env python3
"""
Run script for Meditra Avatar project
Starts the FastAPI server with proper environment
"""
import subprocess
import sys
import os
from pathlib import Path

def main():
    print("🚀 Starting Meditra Avatar server...")
    
    # Check if virtual environment exists
    venv_path = Path(".venv")
    if not venv_path.exists():
        print("❌ Virtual environment not found. Please run 'python setup.py' first.")
        sys.exit(1)
    
    # Determine activation and uvicorn paths
    if os.name == 'nt':  # Windows
        activate_script = ".venv\\Scripts\\activate"
        uvicorn_script = ".venv\\Scripts\\uvicorn"
    else:  # Unix-like
        activate_script = ".venv/bin/activate"
        uvicorn_script = ".venv/bin/uvicorn"
    
    # Check if viseme clips exist
    viseme_dir = Path("app/static/visemes")
    required_visemes = ["ee", "ih", "ah", "oh", "oo", "ma", "pa", "fa", "tha", "ta", "ka", "sha", "pause"]
    missing_visemes = []
    
    if viseme_dir.exists():
        for viseme in required_visemes:
            if not (viseme_dir / f"{viseme}.mp4").exists():
                missing_visemes.append(f"{viseme}.mp4")
    else:
        print(f"⚠️ Warning: Viseme directory not found at {viseme_dir}")
        missing_visemes = [f"{v}.mp4" for v in required_visemes]
    
    if missing_visemes:
        print("⚠️ Warning: Missing viseme clips:")
        for viseme in missing_visemes:
            print(f"   - {viseme}")
        print("The app will start but may not work correctly.")
        print("Add viseme clips to app/static/visemes/ directory.")
    
    # Start the server
    print("🌐 Starting FastAPI server on http://127.0.0.1:8000")
    print("Press Ctrl+C to stop the server")
    
    try:
        if os.name == 'nt':  # Windows
            cmd = f"{uvicorn_script} app.main:app --reload --port 8000"
        else:  # Unix-like
            cmd = f"{activate_script} && uvicorn app.main:app --reload --port 8000"
        
        subprocess.run(cmd, shell=True)
    except KeyboardInterrupt:
        print("\n👋 Server stopped")

if __name__ == "__main__":
    main()