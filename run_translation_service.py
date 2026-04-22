#!/usr/bin/env python3
"""
Start the translation service locally.

Usage:
    python run_translation_service.py
"""
import sys
import os

# Ensure app module can be imported
sys.path.insert(0, os.path.dirname(__file__))

from app.service.draft_service import app
import uvicorn


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)