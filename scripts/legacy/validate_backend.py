#!/usr/bin/env python3
"""
Minimal validation of the model backend endpoint.
"""
import os
import sys
import logging

# Add project to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Set environment variable for the backend URL
os.environ["MODEL_BACKEND_URL"] = "http://192.168.68.61:8001/generate"
os.environ["MODEL_TIMEOUT_SECONDS"] = "30"

from app.config import config
from app.translate.backend_adapter import call_model_backend

logging.basicConfig(level=logging.INFO)

def main():
    print("Testing connection to model backend...")
    print(f"MODEL_BACKEND_URL = {config.MODEL_BACKEND_URL}")
    print(f"MODEL_TIMEOUT_SECONDS = {config.MODEL_TIMEOUT_SECONDS}")

    # Simple prompt
    prompt = "Hello, how are you?"
    print(f"Sending prompt: {prompt}")

    try:
        response = call_model_backend(prompt)
        print(f"SUCCESS! Received response: {response}")
        return 0
    except Exception as e:
        print(f"FAILED! Error: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())