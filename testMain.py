import json

from SoftwareInventoryWinRM import SoftwareInventoryWinRM
from DatabaseManager import DatabaseManager
import csv


def process_host(hostname, db_instance):
    client = SoftwareInventoryWinRM(
        host=hostname
    )
    json_path = f"json\\{hostname}_output.json"
    try:
        client.get_installed_software(json_path)
    except Exception as e:
        print(f"[ERROR] Fehler beim Ausführen des Skripts auf {hostname}: {e}")
        return
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            software_list = json.load(f)
    except Exception as e:
        print(f"[ERROR] Fehler beim Einlesen der JSON-Datei für {hostname}: {e}")
        return
    for entry in software_list:
        if "Hostname" not in entry or not entry["Hostname"]:
            entry["Hostname"] = hostname
    try:
        db_instance.insert_software_to_test(software_list, hostname)
        print(f"[INFO] Daten von {hostname} erfolgreich in die DB geschrieben.")
    except Exception as e:
        print(f"[ERROR] Fehler beim Einfügen in die DB für {hostname}: {e}")

def main():
    db_instance = DatabaseManager()
    db_instance.connect_db()
    db_instance.reset_data_table()
    with open("cache/hosts.csv", newline='', encoding="utf-8") as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            hostname = row['hostname']
            process_host(hostname, db_instance)
    db_instance.db_disconnect()


if __name__ == '__main__':
    main()
