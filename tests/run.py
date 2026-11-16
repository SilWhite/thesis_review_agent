"""Run offline regressions only; live checks are explicitly opt-in."""

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--ui", action="store_true", help="also run Node-based UI contracts"
    )
    args = parser.parse_args()
    cases = sorted((ROOT / "tests/unit").glob("*.py")) + sorted(
        (ROOT / "tests/integration").glob("test_*.py")
    )
    failures = []
    for path in cases:
        with tempfile.TemporaryDirectory(prefix="thesis-test-") as directory:
            command = [sys.executable, str(path)]
            if path.stem == "rule_case_matrix":
                command.append(str(Path(directory) / "matrix.json"))
            env = dict(
                os.environ,
                PYTHONPATH=str(ROOT),
                MODEL_BASE_URL="",
                MODEL_NAME="",
                LANGSMITH_TRACING="false",
            )
            result = subprocess.run(
                command,
                cwd=directory,
                env=env,
                capture_output=True,
                text=True,
                timeout=120,
            )
        print(
            f'{"PASS" if result.returncode == 0 else "FAIL"} {path.relative_to(ROOT)}',
            flush=True,
        )
        if result.returncode:
            failures.append(str(path.relative_to(ROOT)))
            print(result.stdout + result.stderr)
    if args.ui:
        node = shutil.which("node")
        if not node:
            parser.error("--ui requires Node on PATH")
        for path in sorted((ROOT / "tests/ui").glob("*.cjs")):
            result = subprocess.run(
                [node, str(path)], cwd=ROOT, capture_output=True, text=True, timeout=30
            )
            print(
                f'{"PASS" if result.returncode == 0 else "FAIL"} {path.relative_to(ROOT)}'
            )
            if result.returncode:
                failures.append(str(path.relative_to(ROOT)))
                print(result.stdout + result.stderr)
        cases += list((ROOT / "tests/ui").glob("*.cjs"))
    print(f"{len(cases) - len(failures)}/{len(cases)} suites passed")
    return bool(failures)


if __name__ == "__main__":
    sys.exit(main())
