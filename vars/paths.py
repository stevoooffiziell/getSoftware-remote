# -*- coding: utf-8 -*-
"""Zentrale, vom Arbeitsverzeichnis unabhängige Projektpfade."""
import os

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CONFIG_FILE = os.path.join(BASE_DIR, "config", "config.ini")
SECRET_KEY_FILE = os.path.join(BASE_DIR, "config", "secret.key")
HOSTS_CSV = os.path.join(BASE_DIR, "csv", "hosts.csv")
USERS_FILE = os.path.join(BASE_DIR, "users.txt")
LOG_DIR = os.path.join(BASE_DIR, "logs")

os.makedirs(LOG_DIR, exist_ok=True)
