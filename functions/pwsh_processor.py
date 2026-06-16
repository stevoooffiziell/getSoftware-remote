# -*-coding: utf-8 -*-
import json
import csv
import os

from functions.DatabaseManager import DatabaseManager
from functions.SoftwareInventoryWinRM import SoftwareInventoryWinRM
from vars import global_vars

db_instance: DatabaseManager = DatabaseManager()

def process_csv(db_inst):
    hosts_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "csv", "hosts.csv"))
    first = True
    with open(hosts_dir, newline='', encoding="utf-8") as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            if first:
                first = False

            hostname = row['hostname']
            try:
                process_host(hostname, db_inst)
            except Exception as e:
                print(f"{db_inst.get_logprint_error()} Fehler bei Host {hostname}: {e}")
            # Host-Zähler nach jeder Verarbeitung erhöhen
            with global_vars.processed_hosts_lock:
                global_vars.processed_hosts += 1
                print(f"{db_inst.get_logprint_info()} Verarbeiteter Host: {hostname} ({global_vars.processed_hosts}/{global_vars.total_hosts})")

def process_host(hostname, db_inst):
    client = SoftwareInventoryWinRM(
        host=hostname
    )
    current_dir = os.path.dirname(os.path.abspath(__file__))
    json_dir = os.path.join(current_dir, "..", "json", f"{hostname}_output.json")
    json_dir = os.path.normpath(json_dir)
    db_inst.logger.info(f"Processing {hostname}...")
    print(f"\n{db_inst.get_logprint_info()} Processing {hostname}...")

    try:
        client.get_installed_software(json_dir)
    except Exception as e:
        print(f"{db_inst.get_logprint_error()} Failed executing script on {hostname}: {e}")
        if str(e).startswith("the specified credentials"):
            db_inst.logger.error(f"The specified credentials were incorrect")
        else:
            db_inst.logger.error(f"Failed to execute powershell script on {hostname}: {e}")


    try:
        with open(json_dir, "r", encoding="utf-8") as f:
            software_list = json.load(f)

    except Exception as e:
        print(f"{db_inst.get_logprint_error()} Error occurred while reading json-file for {hostname}: {e}")
        return

    for entry in software_list:
        if "Hostname" not in entry or not entry["Hostname"]:
            entry["Hostname"] = hostname
            print(f"Finished checking entries on {hostname}")
    try:
        db_inst.insert_software(software_list, hostname)
        print(f"{db_inst.get_logprint_info()} Data of {hostname} successfully inserted into database.")

    except Exception as e:
        print(f"{db_inst.get_logprint_error()} Error inserting data into database for {hostname}: {e}")