# -*- coding: utf-8 -*-
"""Benutzerverwaltung auf Basis von ``users.txt`` (Format: ``username salt$hash``).

Neuen Benutzer anlegen: ``python -m secret.user_management``
"""
import os
from getpass import getpass

from secret.pwd_management import hash_password, verify_password
from vars.paths import USERS_FILE


def _read_users() -> dict:
    users = {}
    try:
        with open(USERS_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 2:
                    users[parts[0]] = parts[1]
    except FileNotFoundError:
        print(f"User file not found: {USERS_FILE}")
    return users


def user_exists(username: str) -> bool:
    return username in _read_users()


def user_auth(username: str, password: str) -> bool:
    stored = _read_users().get(username)
    return stored is not None and verify_password(password, stored)


def register(username: str, password: str) -> bool:
    if user_exists(username):
        print(f"User {username} already exists")
        return False
    # Fehlenden Zeilenumbruch am Dateiende ergänzen, sonst landet der Eintrag in der letzten Zeile
    needs_newline = False
    if os.path.exists(USERS_FILE) and os.path.getsize(USERS_FILE) > 0:
        with open(USERS_FILE, 'rb') as f:
            f.seek(-1, os.SEEK_END)
            needs_newline = f.read(1) not in (b'\n', b'\r')
    with open(USERS_FILE, 'a', encoding='utf-8') as f:
        f.write(f"{chr(10) if needs_newline else ''}{username} {hash_password(password)}\n")
    print(f"User {username} registered")
    return True


if __name__ == '__main__':
    name = input("Benutzername: ").strip()
    pwd = getpass("Passwort: ")
    if pwd != getpass("Passwort wiederholen: "):
        print("Passwörter stimmen nicht überein.")
    elif name and pwd:
        register(name, pwd)
