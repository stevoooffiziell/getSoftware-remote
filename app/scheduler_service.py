# -*- coding: utf-8 -*-

import logging
import threading
import time

from apscheduler.schedulers.background import BackgroundScheduler

from globals import service_active
from testMain import main as inventory_main
from datetime import datetime

scheduler = BackgroundScheduler()


def init_scheduler():
    if not scheduler.get_jobs():
        # Periodischer Job (alle 2 Wochen)
        scheduler.add_job(
            run_inventory,
            'interval',
            weeks=2,
            id='periodic_inventory',
            next_run_time=datetime.now()
        )

        # Manueller Job (wird bei Bedarf ausgelöst)
        scheduler.add_job(
            run_inventory,
            'date',
            id='manual_run',
            run_date=None  # Wird nicht automatisch ausgeführt
        )


# Logger konfigurieren
logger = logging.getLogger('SchedulerService')
logger.setLevel(logging.INFO)
handler = logging.FileHandler('logs/scheduler.log')
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)


def run_inventory():
    """
    Executes the inventory thread

    :return:
    """
    if not service_active.is_set():
        logger.info("Inventur übersprungen - Service deaktiviert")
        return False

    try:
        logger.info(f"Starting inventory at {datetime.now()}")
        inventory_main()
        logger.info(f"Inventory completed at {datetime.now()}")
        return True
    except Exception as e:
        logger.error(f"Inventory error: {str(e)}")
        return False


def periodic_inventory(interval_weeks=2):
    """
    Periodische Inventur im Hintergrund

    :param interval_weeks:
    """
    while True:
        if service_active.is_set():
            run_inventory()
            sleep_seconds = interval_weeks * 7 * 24 * 3600
            logger.info(f"Nächste Inventur in {interval_weeks} Wochen")
        else:
            sleep_seconds = 10  # Kurzes Intervall bei deaktiviertem Service
            logger.info("Service deaktiviert - Warte auf Aktivierung")

        time.sleep(sleep_seconds)


# Starte periodische Inventur in eigenem Thread
inventory_thread = threading.Thread(
    target=periodic_inventory,
    args=(2,),  # Standardintervall: 2 Wochen
    name="periodic_inventory",
    daemon=True
)
inventory_thread.start()
