path = "/home/amax/anaconda3/envs/qwen3/lib/python3.10/site-packages/vllm/transformers_utils/tokenizer.py"
with open(path, "r", encoding="utf-8") as f:
    c = f.read()
target = "tokenizer.all_special_tokens_extended)"
repl = 'getattr(tokenizer, "all_special_tokens_extended", tokenizer.all_special_tokens))'
if target in c:
    c = c.replace(target, repl)
    with open(path, "w", encoding="utf-8") as f:
        f.write(c)
    print("Patch applied successfully")
else:
    print("Target already patched or not found")
