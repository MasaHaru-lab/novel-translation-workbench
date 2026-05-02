#!/usr/bin/env python3
import requests
import json
import sys

def check_ollama():
    url = "http://localhost:11434/api/generate"
    try:
        # Simple test payload
        payload = {
            "model": "llama3.2:3b",  # or any model likely to be present
            "prompt": "test",
            "stream": False
        }
        response = requests.post(url, json=payload, timeout=5)
        if response.status_code == 200:
            print("Ollama is running and responding.")
            return True
        else:
            print(f"Ollama responded with status {response.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        print("Ollama is not running (connection refused).")
        return False
    except Exception as e:
        print(f"Error checking Ollama: {e}")
        return False

if __name__ == '__main__':
    if check_ollama():
        sys.exit(0)
    else:
        sys.exit(1)