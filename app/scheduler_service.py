# -*- coding: utf-8 -*-
import csv
import logging
import threading
import time
from datetime import datetime, timedelta

import functions.pwsh_processor as _func
from vars.global_vars import service_active
from functions.DatabaseManager import DatabaseManager

# Logger konfigurieren
logger = logging.getLogger('SchedulerService')
logger.setLevel(logging.INFO)
handler = logging.FileHandler('logs/scheduler.log')
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

# DatabaseManager-Instanz
db_manager = DatabaseManager()


def run_inventory():
    """Führt die Inventur durch und aktualisiert Zeitstempel"""
    if not service_active.is_set():
        logger.info("Inventur übersprungen - Service deaktiviert")
        return False

    try:
        # Fortschrittsvariablen setzen
        with globals.processed_hosts_lock:
            globals.inventory_start_time = datetime.now()
            globals.processed_hosts = 0
            with open('csv\\hosts.csv', 'r') as f:
                globals.total_hosts = sum(1 for _ in csv.reader(f)) - 1
            globals.is_running = True

        logger.info(f"Starting inventory at {datetime.now()}")
        _func.main()
        # Aktualisiere Zeitstempel
        end_time = datetime.now()
        next_run = end_time + timedelta(weeks=db_manager.get_metadata("interval_weeks")[0] or 2)

        db_manager.set_metadata("last_inventory_start", end_time.strftime("%Y-%m-%d %H:%M:%S"))
        db_manager.set_metadata("next_inventory_run", next_run.strftime("%Y-%m-%d %H:%M:%S"))

        # Inventur erfolgreich beendet
        with globals.processed_hosts_lock:
            globals.last_run_time = end_time.strftime("%Y-%m-%d %H:%M:%S")
            globals.last_host_count = globals.processed_hosts
            globals.is_running = False

        logger.info(f"Inventory completed at {datetime.now()}")
        return True
    except Exception as e:
        logger.error(f"Inventory error: {str(e)}")
        return False
    finally:
        # Sicherstellen, dass Status zurückgesetzt wird
        with globals.processed_hosts_lock:
            globals.is_running = False

def monitor_schedule():
    """Überwacht kontinuierlich den Inventarisierungszeitplan"""
    logger.info("Inventory schedule monitor started")

    while True:
        try:
            # Hole Zeitstempel aus der Datenbank
            last_run_value = db_manager.get_metadata("last_inventory_start")[0]
            next_run_value = db_manager.get_metadata("next_inventory_run")[0]
            service_active_value = db_manager.get_metadata("service_active")[0]

            logger.debug(f"DB values - last: {last_run_value}, next: {next_run_value}, active: {service_active_value}")

            # Prüfe ob Service aktiv ist
            if service_active_value != "1":
                logger.debug("Service ist deaktiviert - überspringe Prüfung")
                time.sleep(60)
                continue

            # Konvertiere zu datetime-Objekten
            next_run = None
            if next_run_value and next_run_value != "None":
                try:
                    next_run = datetime.strptime(str(next_run_value), "%Y-%m-%d %H:%M:%S")
                except Exception as e:
                    logger.error(f"Fehler beim Parsen von next_run: {str(e)}")

            # Prüfe ob Inventur benötigt wird
            try:
                if next_run and datetime.now() >= next_run:
                    logger.info("Scheduled inventory time reached, starting inventory...")
                    run_inventory()
                else:
                    if next_run:
                        logger.debug(f"Next run: {next_run} (noch nicht erreicht)")
                    else:
                        logger.debug("Kein nächster Laufzeitpunkt gesetzt")
            except Exception as e:
                logger.error(f"Fehler beim Starten von run-inventory: {str(e)}")

            time.sleep(300)  # Prüfe alle 5 Minuten

        except Exception as e:
            logger.error(f"Schedule monitoring error: {str(e)}")
            time.sleep(600)  # Bei Fehler 10 Minuten warten

def start_periodic_inventory():
    """Startet alle Scheduler-Komponenten"""
    # Starte Monitor-Thread
    monitor_thread = threading.Thread(
        target=monitor_schedule,
        name="inventory_monitor",
        daemon=True
    )
    monitor_thread.start()
    logger.info("Inventory schedule monitor thread started")
