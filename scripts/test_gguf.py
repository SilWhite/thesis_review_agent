import importlib.metadata
import traceback
import packaging.version

import importlib.metadata
import traceback
import packaging.version
import transformers.utils.import_utils as u

print("gguf package metadata version:", importlib.metadata.version("gguf"))
print("PACKAGE_DISTRIBUTION_MAPPING has gguf?", "gguf" in u.PACKAGE_DISTRIBUTION_MAPPING)
if "gguf" in u.PACKAGE_DISTRIBUTION_MAPPING:
    print("mapping:", u.PACKAGE_DISTRIBUTION_MAPPING["gguf"])
print("_is_package_available:", u._is_package_available("gguf", return_version=True))

