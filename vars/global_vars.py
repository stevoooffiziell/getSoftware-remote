# -*- coding: utf-8 -*-
"""Gemeinsamer Laufzeitzustand der Inventur (Fortschritt, Service-Status)."""
from threading import Event, Lock

service_active = Event()
service_active.set()

# Fortschrittsvariablen (Zugriff über processed_hosts_lock)
processed_hosts_lock = Lock()
inventory_start_time = None
processed_hosts = 0
total_hosts = 0
is_running = False
last_run_time = None
last_host_count = 0


def get_total_hosts() -> int:
    """Anzahl der Hosts in der Host-CSV, 0 falls nicht lesbar."""
    from functions.pwsh_processor import read_hostnames
    try:
        return len(read_hostnames())
    except OSError:
        return 0
