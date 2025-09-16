import socket
import subprocess
import threading
import logging
import time
import struct

# Logger konfigurieren
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.FileHandler("logs\\scan_network.log"),
        logging.StreamHandler()
    ])


def get_hostname(ip):
    try:
        hostname = socket.gethostbyaddr(ip)[0]
    except Exception as e:
        hostname = f"Exception: {e}"
    return hostname


def ping(ip):
    try:
        result = subprocess.run(
            ['ping', '-n', '1', '-w', '200', ip],
            capture_output=True,
            text=True,
            encoding='cp850',  # Windows-Standard-Encoding für Konsole
            errors='replace'   # Unbekannte Zeichen ersetzen
        )
        output = result.stdout.strip() if result.stdout else ""
        return result.returncode == 0, output
    except Exception as e:
        return False, f"Ping Exception: {e}"


def scan_network(subnet, logfile):
    logging.info(f"    [SCAN]      Starte Scan für Subnetz {subnet}.0/24 ...")
    threads = []
    results = []

    def worker(ip):
        success, ping_output = ping(ip)
        if success:
            hostname = get_hostname(ip)
            if hostname and not hostname.startswith("Exception") and hostname != "Hostname not found":
                msg = f"    [HOSTNAME]  {ip} - {hostname}"
                logmsg = f"{ip} - {hostname}"
                results.append(logmsg)
                logging.info(msg)
            else:
                msg = f" [HOSTNAME]  {ip} - Hostname not found"
                logmsg = f"{ip} - Hostname not found"
                results.append(logmsg)
                logging.warning(msg)
        else:
            msg = f" [HOSTNAME]  {ip} - not reachable"
            logmsg = f"{ip} - not reachable"
            results.append(logmsg)
            logging.warning(msg)
        time.sleep(1)

    for i in range(1, 255):
        ip = f"{subnet}.{i}"
        t = threading.Thread(target=worker, args=(ip,))
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    with open(logfile, "w") as f:
        def ip_key(line):
            ip = line.split(" - ")[0].strip()
            try:
                return struct.unpack('!L', socket.inet_aton(ip))[0]
            except Exception:
                return 0
        for line in sorted(results, key=ip_key):
            f.write(line + "\n")
    logging.info(f"    [SCAN]   Scan für Subnetz {subnet}.0/24 abgeschlossen. Ergebnisse in {logfile}.")

if __name__ == "__main__":
    # Passe das Subnetz an dein Netzwerk an!
    scan_network("10.100.12", "hostnames12.log")
    scan_network("10.100.13", "hostnames13.log")