import json
from pathlib import Path
import sys

root_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root_dir))

from app.storage import Store, sanitize_unicode

def test_surrogate():
    test_dir = root_dir / "data" / "test_store"
    store = Store(test_dir)
    
    # 1. Lone surrogate
    lone = "This is a math formula with lone surrogate: " + chr(0xd835) + " end."
    doc = store.save_document("test.txt", lone.encode("utf-8", "surrogatepass"))
    print("Document saved successfully:", doc["id"])
    
    # 2. Write to store with surrogates in dict/list
    test_val = {
        "text": lone,
        "nested": [lone, "normal text", chr(0xd835) + chr(0xdc00)]
    }
    folder = store.folder("jobs", "job_0123456789abcdef0123456789abcdef")
    store.write(folder, "content.json", test_val)
    print("Store.write executed successfully with surrogates!")
    
    # 3. Read back
    read_back = store.read(folder, "content.json")
    print("Store.read back successfully:", repr(read_back["nested"][1]))
    print("Surrogate test passed completely!")

if __name__ == "__main__":
    test_surrogate()
