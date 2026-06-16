import os
import sys
import subprocess

print("=" * 50)
print("Umgebungs-Check")
print("=" * 50)

print(f"Python Executable: {sys.executable}")
print(f"Python Version: {sys.version}")
print(f"Virtual Environment: {os.getenv('VIRTUAL_ENV', 'Nicht aktiv')}")

# Pip list im aktuellen Environment
try:
    result = subprocess.run([sys.executable, '-m', 'pip', 'list'],
                          capture_output=True, text=True)
    print("\nInstallierte Pakete:")
    for line in result.stdout.split('\n'):
        if 'flask' in line.lower():
            print(f"  {line}")
except Exception as e:
    print(f"Fehler bei pip list: {e}")

# Pfade
print(f"\nPython-Pfade:")
for path in sys.path:
    if 'site-packages' in path:
        print(f"  {path}")