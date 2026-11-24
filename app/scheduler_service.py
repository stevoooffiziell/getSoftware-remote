# -*- coding: utf-8 -*-
"""Inventurlauf (manuell und zeitgesteuert)."""
import logging
import os
import threading
import time
from datetime import datetime, timedelta

import vars.global_vars as gv
from functions.DatabaseManager import DatabaseManager
from functions.pwsh_processor import process_csv
from vars.paths import LOG_DIR

INVENTORY_THREAD_NAME = "manual_inventory_thread"
DEFAULT_INTERVAL_WEEKS = 2

logger = logging.getLogger('SchedulerService')
logger.setLevel(logging.INFO)
if not logger.handlers:
    _handler = logging.FileHandler(os.path.join(LOG_DIR, 'scheduler.log'), encoding="utf-8")
    _handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    logger.addHandler(_handler)

db_manager = DatabaseManager()


def run_inventory():
    """Führt eine komplette Inventur aus und aktualisiert die Metadaten."""
    try:
        start = datetime.now()
        db_manager.set_metadata("last_inventory_start", start)
        logger.info(f"Starting inventory at {start}")

        process_csv(db_manager)

        end = datetime.now()
        interval = db_manager.get_metadata("interval_weeks") or DEFAULT_INTERVAL_WEEKS
        db_manager.set_metadata("last_end_time", end)
        db_manager.set_metadata("next_inventory_run", start + timedelta(weeks=int(interval)))

        with gv.processed_hosts_lock:
            gv.last_run_time = end
            gv.last_host_count = gv.processed_hosts
        logger.info(f"Inventory completed at {end}")
        return True
    except Exception as e:
        logger.error(f"Inventory error: {e}")
        return False
    finally:
        with gv.processed_hosts_lock:
            gv.is_running = False
            gv.inventory_start_time = None


def start_inventory_thread() -> bool:
    """Startet eine Inventur im Hintergrund. ``False``, wenn bereits eine läuft."""
    with gv.processed_hosts_lock:
        if gv.is_running:
            return False
        gv.is_running = True
        gv.inventory_start_time = datetime.now()
        gv.processed_hosts = 0
        gv.total_hosts = gv.get_total_hosts()

    threading.Thread(target=run_inventory, name=INVENTORY_THREAD_NAME, daemon=True).start()
    return True


def monitor_schedule(check_interval: int = 300):
    """Prüft regelmäßig, ob die nächste geplante Inventur fällig ist."""
    logger.info("Inventory schedule monitor started")
    while True:
        try:
            next_run = db_manager.get_metadata("next_inventory_run")
            if (gv.service_active.is_set()
                    and db_manager.get_metadata("service_active") == 1
                    and isinstance(next_run, datetime)
                    and datetime.now() >= next_run):
                logger.info("Scheduled inventory time reached, starting inventory...")
                start_inventory_thread()
        except Exception as e:
            logger.error(f"Schedule monitoring error: {e}")
        time.sleep(check_interval)


def start_periodic_inventory():
    """Startet den Hintergrund-Thread für die zeitgesteuerte Inventur."""
    threading.Thread(target=monitor_schedule, name="inventory_monitor", daemon=True).start()
    logger.info("Inventory schedule monitor thread started")
