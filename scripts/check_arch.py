from vllm.model_executor.models import ModelRegistry
archs = [x for x in ModelRegistry.get_supported_archs() if "qwen" in x.lower()]
print("Supported Qwen architectures in vLLM:")
for a in archs:
    print(" -", a)
