import csv
from threading import Event, Lock

from functions.DatabaseManager import DatabaseManager

db = DatabaseManager()

service_active = Event()
service_active.set()  # Standardm‰ﬂig aktiviert

def get_total_hosts():
    try:
        with open('csv\\hosts.csv', 'r') as f:
            return sum(1 for _ in csv.reader(f)) - 1  # minus header
    except Exception as e:
        return e

# Fortschrittsvariablen
inventory_start_time = None
processed_hosts = 0
total_hosts = get_total_hosts()
is_running = False
last_run_time = db.get_metadata("last_inventory_start")
last_host_count = 0
processed_hosts_lock = Lock()