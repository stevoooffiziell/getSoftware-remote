# -*- coding: utf-8 -*-
import hashlib
import hmac
import os


def _sha256(salt: str, pwd: str) -> str:
    return hashlib.sha256((salt + pwd).encode('utf-8')).hexdigest()


def hash_password(pwd: str) -> str:
    """Hasht ein Passwort mit SHA-256 und zufälligem Salt (Format ``salt$hash``)."""
    salt = os.urandom(16).hex()
    return f"{salt}${_sha256(salt, pwd)}"


def verify_password(pwd: str, stored: str) -> bool:
    """Prüft ein Passwort gegen einen gespeicherten ``salt$hash``-Wert."""
    try:
        salt, stored_hash = stored.split('$', 1)
    except ValueError:
        return False
    return hmac.compare_digest(_sha256(salt, pwd), stored_hash)
