# -*-coding: utf-8 -*-
import csv
import os
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor

from functions.DatabaseManager import PROJECT_ROOT
from functions.SoftwareInventoryWinRM import SoftwareInventoryWinRM
from vars import global_vars

HOSTS_FILE = os.path.join(PROJECT_ROOT, "csv", "hosts.csv")

# Die Laufzeit steckt fast vollständig im Warten auf WinRM-Antworten (bzw. auf
# Timeouts nicht erreichbarer Hosts), deshalb werden mehrere Hosts gleichzeitig
# abgefragt. Die DB-Inserts bleiben über den Lock im DatabaseManager seriell.
MAX_WORKERS = int(os.environ.get("INVENTORY_MAX_WORKERS", "8"))


def read_hostnames(hosts_file=HOSTS_FILE):
    with open(hosts_file, newline='', encoding="utf-8") as csvfile:
        return [
            row['hostname'].strip()
            for row in csv.DictReader(csvfile)
            if (row.get('hostname') or '').strip()
        ]


def process_csv(db_inst):
    hostnames = read_hostnames()
    with global_vars.processed_hosts_lock:
        global_vars.total_hosts = len(hostnames)

    def worker(hostname):
        try:
            process_host(hostname, db_inst)
        except Exception as e:
            print(f"{db_inst.get_logprint_error()} Fehler bei Host {hostname}: {e}")
        # Host-Zähler nach jeder Verarbeitung erhöhen
        with global_vars.processed_hosts_lock:
            global_vars.processed_hosts += 1
            print(f"{db_inst.get_logprint_info()} Verarbeiteter Host: {hostname} "
                  f"({global_vars.processed_hosts}/{global_vars.total_hosts})")

    with ThreadPoolExecutor(max_workers=max(1, MAX_WORKERS),
                            thread_name_prefix="inventory_worker") as pool:
        # list() wartet auf alle Hosts; worker fängt Fehler selbst ab
        list(pool.map(worker, hostnames))


def process_host(hostname, db_inst):
    db_inst.logger.info(f"Processing {hostname}...")
    print(f"\n{db_inst.get_logprint_info()} Processing {hostname}...")

    try:
        client = SoftwareInventoryWinRM(host=hostname)
        software_list = client.get_installed_software()
    except Exception as e:
        print(f"{db_inst.get_logprint_error()} Failed executing script on {hostname}: {e}")
        if "the specified credentials" in str(e):
            db_inst.logger.error(f"The specified credentials were incorrect ({hostname})")
        else:
            db_inst.logger.error(f"Failed to execute powershell script on {hostname}: {e}")
        # Ohne frische Daten nichts einfügen (sonst landen alte JSON-Stände erneut in der DB)
        return

    try:
        db_inst.insert_software(software_list, hostname)
        print(f"{db_inst.get_logprint_info()} Data of {hostname} successfully inserted into database.")
    except Exception as e:
        print(f"{db_inst.get_logprint_error()} Error inserting data into database for {hostname}: {e}")


def run_inventory_cycle(db_inst):
    """
    Führt eine komplette Inventur durch und pflegt Zeitstempel und Zähler.
    Der Aufrufer muss vorher ``global_vars.begin_run()`` erfolgreich aufgerufen haben.

    :return: Endzeitpunkt der Inventur
    """
    try:
        db_inst.set_starttime(datetime.now())
        process_csv(db_inst)

        end_time = datetime.now()
        interval_weeks = int(db_inst.get_metadata("interval_weeks") or 2)
        db_inst.set_nexttime(end_time + timedelta(weeks=interval_weeks))

        with global_vars.processed_hosts_lock:
            global_vars.last_run_time = end_time
            global_vars.last_host_count = global_vars.processed_hosts
        return end_time
    finally:
        global_vars.end_run()
