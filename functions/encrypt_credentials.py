# -*- coding: utf-8 -*-
"""Verschlüsselt ein Passwort für die config.ini.

Aufruf: ``python -m functions.encrypt_credentials``
"""
import getpass
import os

from cryptography.fernet import Fernet

from vars.paths import SECRET_KEY_FILE


def load_or_create_key(key_path: str = SECRET_KEY_FILE) -> bytes:
    if os.path.exists(key_path):
        with open(key_path, "rb") as f:
            print(f"Bestehender Schlüssel aus '{key_path}' wurde geladen.")
            return f.read()
    os.makedirs(os.path.dirname(key_path), exist_ok=True)
    key = Fernet.generate_key()
    with open(key_path, "wb") as f:
        f.write(key)
    print(f"Neuer Schlüssel wurde unter '{key_path}' gespeichert.")
    return key


if __name__ == '__main__':
    password = getpass.getpass("Bitte Passwort eingeben: ")
    encrypted = Fernet(load_or_create_key()).encrypt(password.encode())
    print("\nVerschlüsseltes Passwort (in die config.ini eintragen):")
    print(encrypted.decode())
