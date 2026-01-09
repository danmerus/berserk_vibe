"""
Build script to create .exe using PyInstaller.

Usage:
    pip install pyinstaller
    python build.py
"""
import subprocess
import sys

def build():
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",           # Single .exe file
        "--windowed",          # No console window
        "--name", "Berserk",   # Output name
        "--icon", "NONE",      # No icon (add later if needed)
        "main.py"
    ]

    print("Building Berserk.exe...")
    print(f"Command: {' '.join(cmd)}")

    result = subprocess.run(cmd)

    if result.returncode == 0:
        print("\n" + "="*50)
        print("Build successful!")
        print("Find your exe at: dist/Berserk.exe")
        print("="*50)
    else:
        print("\nBuild failed!")

if __name__ == "__main__":
    build()
