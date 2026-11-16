import gguf

reader = gguf.GGUFReader("/data01/llms/Qwen3.8-27B-Q8_0.gguf")
print("Architecture:", reader.fields.get("general.architecture", None))
print("Name:", reader.fields.get("general.name", None))
print("Context length:", reader.fields.get("qwen2.context_length", reader.fields.get("general.context_length", None)))
for k, v in list(reader.fields.items())[:20]:
    if not isinstance(v.data, (bytes, bytearray)):
        print(f"{k}: {v.data[:5] if isinstance(v.data, list) else v.data}")
