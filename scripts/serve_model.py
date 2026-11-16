"""Lightweight OpenAI-compatible server for Qwen3.8-27B on Dual GPUs (GPU 1, 2)."""

import os
import sys
import time
import json
import torch
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Union
from transformers import AutoModelForCausalLM, AutoTokenizer

MODEL_PATH = os.getenv("MODEL_PATH", "/data01/llms/Qwen3.8-27B")
PORT = int(os.getenv("PORT", "8122"))
HOST = os.getenv("HOST", "127.0.0.1")

app = FastAPI(title="Qwen3.8-27B OpenAI Server")

tokenizer = None
model = None

class Message(BaseModel):
    role: str
    content: str

class ChatCompletionRequest(BaseModel):
    model: str
    messages: List[Message]
    temperature: Optional[float] = 0.1
    max_tokens: Optional[int] = 4096
    response_format: Optional[Dict[str, Any]] = None

@app.on_event("startup")
def load_model():
    global tokenizer, model
    print(f"Loading tokenizer from {MODEL_PATH}...", flush=True)
    tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH, trust_remote_code=True)
    
    print(f"Loading model on dual GPUs across CUDA_VISIBLE_DEVICES={os.getenv('CUDA_VISIBLE_DEVICES')}...", flush=True)
    start_t = time.time()
    model = AutoModelForCausalLM.from_pretrained(
        MODEL_PATH,
        device_map="auto",
        torch_dtype=torch.bfloat16,
        trust_remote_code=True
    )
    model.eval()
    print(f"Model loaded successfully in {time.time() - start_t:.2f}s!", flush=True)

@app.get("/health")
def health():
    return {"status": "ok", "model_loaded": model is not None}

@app.get("/v1/models")
def list_models():
    return {
        "object": "list",
        "data": [
            {
                "id": "Qwen3.8-27B",
                "object": "model",
                "created": int(time.time()),
                "owned_by": "local"
            }
        ]
    }

@app.post("/v1/chat/completions")
def chat_completion(req: ChatCompletionRequest):
    global tokenizer, model
    if model is None or tokenizer is None:
        raise HTTPException(status_code=503, detail="Model is loading")

    # Format messages using chat template
    raw_msgs = [{"role": m.role, "content": m.content} for m in req.messages]
    
    text = tokenizer.apply_chat_template(
        raw_msgs,
        tokenize=False,
        add_generation_prompt=True
    )
    
    input_device = next(model.parameters()).device
    model_inputs = {k: v.to(input_device) for k, v in tokenizer([text], return_tensors="pt").items()}
    input_len = model_inputs["input_ids"].shape[1]
    
    t0 = time.time()
    print(f"[{time.strftime('%H:%M:%S')}] Received review prompt, prompt_tokens={input_len}, generating...", flush=True)
    
    pad_id = tokenizer.pad_token_id if tokenizer.pad_token_id is not None else tokenizer.eos_token_id
    gen_kwargs = {
        "max_new_tokens": min(req.max_tokens or 2048, 2048),
        "do_sample": False,
        "pad_token_id": pad_id,
        "eos_token_id": tokenizer.eos_token_id,
    }
    
    try:
        with torch.no_grad():
            generated_ids = model.generate(
                **model_inputs,
                **gen_kwargs
            )
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
    
    output_ids = generated_ids[0][input_len:]
    cost_t = time.time() - t0
    print(f"[{time.strftime('%H:%M:%S')}] Finished generation: {len(output_ids)} tokens in {cost_t:.2f}s ({len(output_ids)/max(cost_t, 0.01):.1f} tok/s)", flush=True)
    response_text = tokenizer.decode(output_ids, skip_special_tokens=True).strip()

    # Clean potential markdown wrapping if json is expected
    if req.response_format and req.response_format.get("type") == "json_object":
        clean_text = response_text
        if clean_text.startswith("```json"):
            clean_text = clean_text[7:]
        elif clean_text.startswith("```"):
            clean_text = clean_text[3:]
        if clean_text.endswith("```"):
            clean_text = clean_text[:-3]
        response_text = clean_text.strip()

    return {
        "id": f"chatcmpl-{int(time.time())}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": req.model,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": response_text
                },
                "finish_reason": "stop"
            }
        ],
        "usage": {
            "prompt_tokens": input_len,
            "completion_tokens": len(output_ids),
            "total_tokens": input_len + len(output_ids)
        }
    }

if __name__ == "__main__":
    uvicorn.run(app, host=HOST, port=PORT, log_level="info")
