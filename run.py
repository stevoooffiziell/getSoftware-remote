from app import app
from scheduler_service import start_periodic_inventory
from DatabaseManager import DatabaseManager

db_manager = DatabaseManager()

if __name__ == '__main__':
    # Initialisiere Metadaten
    if not db_manager.get_metadata("interval_weeks"):
        db_manager.set_metadata("interval_weeks", "2")

    # Starte periodische Inventur im Hintergrund
    interval = int(db_manager.get_metadata("interval_weeks")[0] or 2)
    start_periodic_inventory(interval)

    # Starte Flask-App
    app.run(host='0.0.0.0', port=5000, debug=False)