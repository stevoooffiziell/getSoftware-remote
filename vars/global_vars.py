import csv
import os
from datetime import datetime
from threading import Event, Lock

from functions.DatabaseManager import DatabaseManager, PROJECT_ROOT

db = DatabaseManager()

HOSTS_FILE = os.path.join(PROJECT_ROOT, "csv", "hosts.csv")

service_active = Event()
service_active.set()


def get_total_hosts():
    """Anzahl der Hosts in der hosts.csv (ohne Kopfzeile), 0 falls nicht lesbar."""
    try:
        with open(HOSTS_FILE, newline='', encoding="utf-8") as f:
            return sum(1 for row in csv.DictReader(f) if (row.get('hostname') or '').strip())
    except OSError:
        return 0


# Fortschrittsvariablen
inventory_start_time = None
processed_hosts = 0
total_hosts = get_total_hosts()
is_running = False
last_run_time = db.get_metadata("last_inventory_start")  # datetime oder None
last_host_count = 0
processed_hosts_lock = Lock()


def begin_run():
    """
    Markiert atomar den Start einer Inventur.

    :return: ``False``, wenn bereits eine Inventur läuft
    """
    global inventory_start_time, processed_hosts, is_running
    with processed_hosts_lock:
        if is_running:
            return False
        is_running = True
        processed_hosts = 0
        inventory_start_time = datetime.now()
        return True


def end_run():
    """Setzt den Inventurstatus zurück."""
    global inventory_start_time, is_running
    with processed_hosts_lock:
        is_running = False
        inventory_start_time = None
