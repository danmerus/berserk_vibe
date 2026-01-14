"""
Build script to create .exe using PyInstaller.

Usage:
    pip install pyinstaller
    python build.py

This will create a standalone .exe file in the dist/ folder
that includes all game assets (cards, sounds, fonts, etc.)
"""
import subprocess
import sys
import os

def build():
    # Data directories to include
    # Format: (source_path, destination_in_exe)
    data_dirs = [
        ("data/cards", "data/cards"),
        ("data/sounds", "data/sounds"),
        ("data/fonts", "data/fonts"),
        ("data/die", "data/die"),
        ("data/misc", "data/misc"),
        ("data/decks", "data/decks"),
        ("data/bg", "data/bg"),
    ]

    # Build --add-data arguments
    # Windows uses ; as separator, Unix uses :
    separator = ";" if sys.platform == "win32" else ":"

    add_data_args = []
    for src, dst in data_dirs:
        if os.path.exists(src):
            add_data_args.extend(["--add-data", f"{src}{separator}{dst}"])
            print(f"Including: {src} -> {dst}")
        else:
            print(f"Warning: {src} not found, skipping")

    # Hidden imports that PyInstaller might miss
    hidden_imports = [
        "asyncio",
        "ssl",
        "src.network",
        "src.network.server",
        "src.network.client",
        "src.network.protocol",
        "src.network.session",
    ]

    hidden_import_args = []
    for module in hidden_imports:
        hidden_import_args.extend(["--hidden-import", module])

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",           # Single .exe file
        "--windowed",          # No console window
        "--name", "Berserk",   # Output name
        "--icon", "NONE",      # No icon (add later if needed)
        *add_data_args,        # Include data directories
        *hidden_import_args,   # Include hidden imports
        "main.py"
    ]

    print("\n" + "="*50)
    print("Building Berserk.exe...")
    print("="*50)
    print(f"\nCommand: {' '.join(cmd)}\n")

    result = subprocess.run(cmd)

    if result.returncode == 0:
        print("\n" + "="*50)
        print("Build successful!")
        print("Find your exe at: dist/Berserk.exe")
        print("="*50)
        print("\nNote: The exe is self-contained and can be")
        print("distributed to users without Python installed.")
    else:
        print("\nBuild failed!")
        print("Make sure PyInstaller is installed: pip install pyinstaller")

if __name__ == "__main__":
    build()
