# -*- coding: utf-8 -*-
import logging
import time
from datetime import datetime
from globals import service_active

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
    """
    if not service_active.is_set():
        logger.info("Inventur übersprungen - Service deaktiviert")
        return False

    try:
        logger.info(f"Starting inventory at {datetime.now()}")
        from testMain import main as inventory_main
        inventory_main()
        logger.info(f"Inventory completed at {datetime.now()}")
        return True
    except Exception as e:
        logger.error(f"Inventory error: {str(e)}")
        return False


def periodic_inventory(interval_weeks=2):
    """
    Periodische Inventur im Hintergrund
    """
    while True:
        if service_active.is_set():
            try:
                run_inventory()
            except Exception as e:
                logger.error(f"Error in periodic inventory: {str(e)}")

            sleep_seconds = interval_weeks * 7 * 24 * 3600
            logger.info(f"Nächste Inventur in {interval_weeks} Wochen")
        else:
            sleep_seconds = 10  # Kurzes Intervall bei deaktiviertem Service
            logger.info("Service deaktiviert - Warte auf Aktivierung")

        time.sleep(sleep_seconds)