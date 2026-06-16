import socket
import subprocess
import threading
import logging
import time
import struct
import os

# Logger konfigurieren
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%d-%m-%Y %H:%M:%S',
    handlers=[
        logging.FileHandler("logs\\scan_network.log"),
        logging.StreamHandler()
    ]
)

# Globale Menge für eindeutige Einträge
all_entries = set()

def load_existing_entries():
    """Lädt vorhandene Einträge aus der CSV-Datei"""
    global all_entries
    if os.path.exists("host-test.csv"):
        try:
            with open("host-test.csv", "r") as f:
                lines = f.readlines()
                for line in lines[1:]:  # Überspringe Header
                    hostname = line.strip()
                    if hostname and hostname != "hostname":
                        all_entries.add(hostname)
        except Exception as e:
            logging.error(f"Fehler beim Lesen der CSV: {e}")

def append_entry(host):
    if (host and
        host not in all_entries and
        host != "Hostname not found" and
        not host.startswith("Exception") and
        host.endswith(".pfenning.local")):
        all_entries.add(host)
        return True
    return False

def get_hostname(ip):
    try:
        hostname = socket.gethostbyaddr(ip)[0]
        return hostname
    except socket.herror:
        return "Hostname not found"
    except Exception as e:
        return f"Exception: {e}"

def ping(ip):
    try:
        result = subprocess.run(
            ['ping', '-n', '1', '-w', '200', ip],
            capture_output=True,
            text=True,
            encoding='cp850',
            errors='replace'
        )
        output = result.stdout.strip() if result.stdout else ""
        return result.returncode == 0, output
    except Exception as e:
        return False, f"Ping Exception: {e}"

def scan_network(subnet, logfile):
    logging.info(f"[SCAN] Starte Scan für Subnetz {subnet}.0/24 ...")
    results = []
    lock = threading.Lock()
    semaphore = threading.Semaphore(50)  # Weniger Threads für bessere Stabilität

    def worker(ip):
        with semaphore:
            success, ping_output = ping(ip)
            hostname = get_hostname(ip) if success else "not reachable"

            logmsg = f"{ip} - {hostname}"
            with lock:
                results.append(logmsg)

            msg = f"[HOSTNAME] {logmsg}"

            if "not reachable" in hostname or "Exception" in hostname or "not found" in hostname:
                logging.warning(msg)
            else:
                logging.info(msg)
                if success:
                    with lock:
                        if append_entry(hostname):
                            logging.info(f"[ADDED] {hostname} zur CSV hinzugefügt")

            time.sleep(0.1)

    threads = []
    for i in range(1, 255):
        ip = f"{subnet}.{i}"
        t = threading.Thread(target=worker, args=(ip,))
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    # IP-Sortierung für Log-Datei
    def ip_key(line):
        ip = line.split(" - ")[0].strip()
        try:
            return struct.unpack('!L', socket.inet_aton(ip))[0]
        except Exception:
            return 0

    sorted_results = sorted(results, key=ip_key)

    # Log-Datei schreiben
    with open(logfile, "w") as f:
        for line in sorted_results:
            f.write(line + "\n")

    # CSV-Datei schreiben (alphabetisch sortiert)
    sorted_csv_entries = sorted(all_entries)
    with open("host-test.csv", "w") as f:
        f.write("hostname\n")
        for hostname in sorted_csv_entries:
            f.write(hostname + "\n")

    logging.info(f"[SCAN] Scan für Subnetz {subnet}.0/24 abgeschlossen. Ergebnisse in {logfile}")