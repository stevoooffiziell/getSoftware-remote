# -*- coding: utf-8 -*-
import csv

from functions.SoftwareInventoryWinRM import SoftwareInventoryWinRM
from vars import global_vars
from vars.paths import HOSTS_CSV


def read_hostnames(path: str = HOSTS_CSV) -> list:
    """Liest die Hostnamen aus der Host-CSV (Spalte ``hostname``)."""
    with open(path, newline='', encoding="utf-8") as csvfile:
        return [row['hostname'].strip() for row in csv.DictReader(csvfile) if row.get('hostname', '').strip()]


def process_csv(db_inst):
    """Inventarisiert alle Hosts aus der Host-CSV nacheinander."""
    for hostname in read_hostnames():
        try:
            process_host(hostname, db_inst)
        except Exception as e:
            db_inst.logger.error(f"Error processing {hostname}: {e}")
            print(f"{db_inst.get_logprint_error()} Fehler bei Host {hostname}: {e}")
        with global_vars.processed_hosts_lock:
            global_vars.processed_hosts += 1
            print(f"{db_inst.get_logprint_info()} Verarbeiteter Host: {hostname} "
                  f"({global_vars.processed_hosts}/{global_vars.total_hosts})")


def process_host(hostname, db_inst):
    """Liest die Software eines Hosts aus und schreibt sie in die Datenbank."""
    db_inst.logger.info(f"Processing {hostname}...")
    print(f"\n{db_inst.get_logprint_info()} Processing {hostname}...")

    software_list = SoftwareInventoryWinRM(host=hostname).get_installed_software()
    db_inst.insert_software(software_list, hostname)
    print(f"{db_inst.get_logprint_info()} Data of {hostname} successfully inserted into database.")
