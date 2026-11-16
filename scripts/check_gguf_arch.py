import transformers
from transformers.modeling_gguf_pytorch_utils import GGUF_CONFIG_MAPPING

print("qwen35 in GGUF_CONFIG_MAPPING:", "qwen35" in GGUF_CONFIG_MAPPING)
print("qwen in GGUF_CONFIG_MAPPING:", [k for k in GGUF_CONFIG_MAPPING.keys() if "qwen" in k])
