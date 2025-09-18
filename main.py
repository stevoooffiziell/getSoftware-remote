# -*- coding: utf-8 -*-

from functions.scan_network_hostnames import scan_network, load_existing_entries
import os

if __name__ == '__main__':
    # Sicherstellen, dass das Log-Verzeichnis existiert
    os.makedirs("logs", exist_ok=True)

    # Netzwerk-Scans durchführen
    scan_network("10.100.12", "logs\\12-net.log")
    load_existing_entries()
    scan_network("10.100.13", "logs\\13-net.log")