# -*- coding: utf-8 -*-
import getpass
from cryptography.fernet import Fernet
import os

# Verzeichnispfad
key_path = "../config/secret.key"
os.makedirs(os.path.dirname(key_path), exist_ok=True)

# Benutzer-Passwort sicher abfragen
password = getpass.getpass("Bitte Passwort eingeben: ")
print("✅ Passwort wurde erfasst.")

# Schlüssel generieren oder bestehenden wiederverwenden
if not os.path.exists(key_path):
    key = Fernet.generate_key()
    with open(key_path, "wb") as f:
        f.write(key)
    print(f"🔑 Neuer Schluessel wurde unter '{key_path}' gespeichert.")
else:
    with open(key_path, "rb") as f:
        key = f.read()
    print(f"🔑 Bestehender Schluessel aus '{key_path}' wurde geladen.")
    fernet = Fernet(key)


# Verschlüsselung

encrypted = fernet.encrypt(password.encode())
print("\nVerschlüsseltes Passwort (füge das in deine config.ini ein):")
print(encrypted.decode())
