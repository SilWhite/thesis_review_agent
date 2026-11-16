import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
import time

model_path = "/data01/llms/Qwen3.8-27B"
print("Testing loading model with transformers...")
start = time.time()

tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)
print("Tokenizer loaded in {:.2f}s".format(time.time() - start))

# Test with 8-bit or bfloat16
print("Testing device 1 memory...")
gpu_mem = torch.cuda.get_device_properties(1).total_memory / (1024**3)
print("GPU 1 total memory: {:.2f} GB".format(gpu_mem))

print("Loading model on cuda:1...")
model = AutoModelForCausalLM.from_pretrained(
    model_path,
    device_map={"": "cuda:1"},
    torch_dtype=torch.bfloat16,
    trust_remote_code=True
)
print("Model loaded successfully in {:.2f}s!".format(time.time() - start))
allocated = torch.cuda.memory_allocated(1) / (1024**3)
reserved = torch.cuda.memory_reserved(1) / (1024**3)
print("Memory allocated: {:.2f} GB, reserved: {:.2f} GB".format(allocated, reserved))
