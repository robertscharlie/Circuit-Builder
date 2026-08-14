"""Runs every test script in this folder as a subprocess and reports pass/fail.

These are standalone assertion scripts (not pytest), so run.py -m per file:
    python tests/run_all.py
"""
import subprocess
import sys
from pathlib import Path

TESTS_DIR = Path(__file__).parent
SCRIPTS = [
    "smoke_test.py",
    "test_fixes.py",
    "test_polish.py",
    "test_bugfixes.py",
    "test_interactions.py",
    "test_shortcuts_and_save.py",
    "test_new_shortcuts.py",
    "test_split_wire.py",
    "test_move_via_menu.py",
    "test_detach_terminal.py",
    "test_auto_connect.py",
    "test_click_region.py",
]

failed = []
for name in SCRIPTS:
    print(f"--- {name} ---")
    result = subprocess.run([sys.executable, str(TESTS_DIR / name)])
    if result.returncode != 0:
        failed.append(name)

print()
if failed:
    print(f"FAILED: {', '.join(failed)}")
    sys.exit(1)
print(f"ALL {len(SCRIPTS)} TEST SCRIPTS PASSED")
