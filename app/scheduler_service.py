# -*- coding: utf-8 -*-
import logging
import threading
import time
from datetime import datetime, timedelta
from globals import service_active
from DatabaseManager import DatabaseManager

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
    """
    Führt die Inventur durch
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
    logger.info(f"Periodic inventory scheduler started with {interval_weeks} weeks interval")

    while True:
        if service_active.is_set():
            try:
                # Letzten Lauf abrufen
                last_run_str = db_manager.get_metadata("last_run")
                last_run = datetime.strptime(last_run_str, "%Y-%m-%d %H:%M:%S") if last_run_str else None

                # Intervall aus Datenbank abrufen (kann sich ändern)
                current_interval = int(db_manager.get_metadata("interval_weeks") or interval_weeks)

                # Prüfen ob Inventur benötigt wird
                run_now = False
                if not last_run:
                    run_now = True
                else:
                    next_run = last_run + timedelta(weeks=current_interval)
                    if datetime.now() >= next_run:
                        run_now = True

                if run_now:
                    logger.info("Inventory interval reached, starting inventory...")
                    if run_inventory():
                        # Letzten Lauf aktualisieren
                        db_manager.set_metadata("last_run", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                        logger.info("Inventory completed and last run updated")

                    # Nächstes Intervall basierend auf aktuellem Zeitpunkt
                    sleep_seconds = current_interval * 7 * 24 * 3600
                else:
                    # Zeit bis zum nächsten Lauf berechnen
                    next_run = last_run + timedelta(weeks=current_interval)
                    sleep_seconds = (next_run - datetime.now()).total_seconds()
                    logger.info(
                        f"Next inventory scheduled at {next_run}, sleeping for {sleep_seconds / 3600:.1f} hours")
            except Exception as e:
                logger.error(f"Error in periodic inventory: {str(e)}")
                # Fallback: Standardintervall bei Fehlern
                sleep_seconds = interval_weeks * 7 * 24 * 3600
        else:
            sleep_seconds = 10  # Kurzes Intervall bei deaktiviertem Service
            logger.info("Service deaktiviert - Warte auf Aktivierung")

        time.sleep(sleep_seconds)


def start_periodic_inventory(interval_weeks=2):
    """Startet den periodischen Inventur-Thread"""
    logger.info(f"Starting periodic inventory thread with interval: {interval_weeks} weeks")

    thread = threading.Thread(
        target=periodic_inventory,
        args=(interval_weeks,),
        name="periodic_inventory",
        daemon=True
    )
    thread.start()