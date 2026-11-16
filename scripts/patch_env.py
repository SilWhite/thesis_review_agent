from pathlib import Path

# Fix gguf __version__
gguf_init = Path("/home/amax/anaconda3/envs/qwen3/lib/python3.10/site-packages/gguf/__init__.py")
if gguf_init.exists():
    content = gguf_init.read_text(encoding="utf-8")
    lines = [line for line in content.splitlines(keepends=True) if not line.startswith("__version__")]
    lines.insert(0, '__version__ = "0.18.0"\n')
    gguf_init.write_text("".join(lines), encoding="utf-8")
    print("Fixed gguf/__init__.py")

# Test is_gguf_available
import transformers.utils.import_utils as u
print("is_gguf_available:", u.is_gguf_available())
