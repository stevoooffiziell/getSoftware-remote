from apscheduler.schedulers.background import BackgroundScheduler
from testMain import main as inventory_main
from datetime import datetime

scheduler = BackgroundScheduler()


def run_inventory():
    print(f"{datetime.now()} - Starting inventory collection...")
    try:
        inventory_main()
        print(f"{datetime.now()} - Inventory completed successfully")
    except Exception as e:
        print(f"{datetime.now()} - Error during inventory: {str(e)}")


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


# Initialisiere den Scheduler
init_scheduler()

if __name__ == '__main__':
    scheduler.start()
    try:
        while True:
            pass
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()