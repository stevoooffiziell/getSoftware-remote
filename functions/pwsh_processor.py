# -*-coding: utf-8 -*-
import json
import csv
from functions.DatabaseManager import DatabaseManager
from functions.SoftwareInventoryWinRM import SoftwareInventoryWinRM
import vars.global_vars

db_instance: DatabaseManager = DatabaseManager()

def process_csv(db_inst):
    first = True
    with open("../csv/hosts.csv", newline='', encoding="utf-8") as csvfile:
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
            with globals.processed_hosts_lock:
                globals.processed_hosts += 1
                print(f"Verarbeiteter Host: {hostname} ({globals.processed_hosts}/{globals.total_hosts})")

def process_host(hostname, db_inst):
    client = SoftwareInventoryWinRM(
        host=hostname
    )
    json_path = f"json\\{hostname}_output.json"
    db_inst.logger.info(f"Processing {hostname}...")
    print(f"\n{db_inst.get_logprint_info()} Processing {hostname}...")

    try:
        client.get_installed_software(json_path)
    except Exception as e:
        print(f"{db_inst.get_logprint_error()} Failed executing script on {hostname}: {e}")
        db_inst.logger.error(f"Failed to execute powershell script on {hostname}: {e}")

    try:
        with open(json_path, "r", encoding="utf-8") as f:
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



def main():
    process_csv(db_instance)