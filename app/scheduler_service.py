# -*- coding: utf-8 -*-
import logging
import os
import threading
import time
from datetime import datetime

import vars.global_vars as gv
from functions.DatabaseManager import DatabaseManager, LOG_DIR
from functions.pwsh_processor import run_inventory_cycle

# Logger konfigurieren
os.makedirs(LOG_DIR, exist_ok=True)
logger = logging.getLogger('SchedulerService')
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.FileHandler(os.path.join(LOG_DIR, 'scheduler.log'), encoding='utf-8')
    handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    logger.addHandler(handler)

# DatabaseManager-Instanz
db_manager = DatabaseManager()

CHECK_INTERVAL_SEC = 300   # Zeitplan alle 5 Minuten prüfen
INACTIVE_INTERVAL_SEC = 60
ERROR_INTERVAL_SEC = 600   # Bei Fehler 10 Minuten warten


def run_inventory():
    """
    Führt die Inventur durch und aktualisiert Zeitstempel

    :return: ``True`` bei Erfolg
    """
    if not gv.service_active.is_set():
        logger.info("Inventur übersprungen - Service deaktiviert")
        return False

    if not gv.begin_run():
        logger.info("Inventur übersprungen - es läuft bereits eine Inventur")
        return False

    try:
        logger.info(f"Starting inventory at {datetime.now()}")
        end_time = run_inventory_cycle(db_manager)
        logger.info(f"Inventory completed at {end_time}")
        return True
    except Exception as e:
        logger.error(f"Inventory error: {str(e)}")
        return False


def monitor_schedule():
    """Überwacht kontinuierlich den Inventarisierungszeitplan"""
    logger.info("Inventory schedule monitor started")

    while True:
        try:
            if db_manager.get_metadata("service_active") != 1:
                logger.debug("Service ist deaktiviert - überspringe Prüfung")
                time.sleep(INACTIVE_INTERVAL_SEC)
                continue

            next_run = db_manager.get_metadata("next_inventory_run")
            if isinstance(next_run, datetime) and datetime.now() >= next_run:
                logger.info("Scheduled inventory time reached, starting inventory...")
                run_inventory()
            elif next_run:
                logger.debug(f"Next run: {next_run} (noch nicht erreicht)")
            else:
                logger.debug("Kein nächster Laufzeitpunkt gesetzt")

            time.sleep(CHECK_INTERVAL_SEC)
        except Exception as e:
            logger.error(f"Schedule monitoring error: {str(e)}")
            time.sleep(ERROR_INTERVAL_SEC)


def start_periodic_inventory():
    """Startet alle Scheduler-Komponenten"""
    monitor_thread = threading.Thread(
        target=monitor_schedule,
        name="inventory_monitor",
        daemon=True
    )
    monitor_thread.start()
    logger.info("Inventory schedule monitor thread started")
