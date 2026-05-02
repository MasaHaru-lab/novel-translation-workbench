#!/usr/bin/env python3
"""
Mock backend server that returns a fixed polished response different from draft.
"""
import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel
import time

app = FastAPI(title="Mock Model Backend")

class GenerateRequest(BaseModel):
    prompt: str
    # Add other fields that might be expected
    model: str = "qwen2.5:14b"
    stream: bool = False

@app.post("/generate")
async def generate(request: GenerateRequest):
    """Mock backend that always returns a polished version different from draft."""
    # Extract some info from prompt for logging
    prompt_preview = request.prompt[:100] + "..." if len(request.prompt) > 100 else request.prompt
    print(f"Mock backend received prompt ({len(request.prompt)} chars): {prompt_preview}")
    print(f"Full request dict: {request.dict()}")

    # Return a fixed polished response that's different from draft
    # This response simulates what a real polish step might produce
    polished_response = """[POLISHED] The Young Lady called the Prince, then departed from the room.

This polished translation improves fluency while preserving the original meaning.
The Chinese comma has been replaced with an English comma, and the sentence
structure has been slightly adjusted for natural English flow."""

    # Simulate some processing time
    time.sleep(0.5)

    return {"text": polished_response}

@app.get("/health")
async def health():
    return {"status": "healthy"}

if __name__ == "__main__":
    print("Starting mock backend on http://localhost:9999")
    print("Use MODEL_BACKEND_URL=http://localhost:9999/generate")
    uvicorn.run(app, host="0.0.0.0", port=9999)