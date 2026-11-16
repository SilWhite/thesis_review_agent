import os
os.environ["CUDA_VISIBLE_DEVICES"] = "2"

print("Testing loading Qwen3.8-27B-Q8_0.gguf via vLLM on GPU 2...")
try:
    from vllm import LLM, SamplingParams
    llm = LLM(
        model="/data01/llms/Qwen3.8-27B-Q8_0.gguf",
        tokenizer="Qwen/Qwen2.5-32B-Instruct", # or what tokenizer? Wait, let's check what tokenizer is used or if GGUF has tokenizer
        gpu_memory_utilization=0.9,
        max_model_len=8192,
        trust_remote_code=True,
    )
    print("Successfully initialized LLM!")
    output = llm.generate("Hello, who are you?", SamplingParams(max_tokens=20))
    print("Output:", output[0].outputs[0].text)
except Exception as e:
    import traceback
    traceback.print_exc()
