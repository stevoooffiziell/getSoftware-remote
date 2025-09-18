from app import app as app
from app.scheduler_service import start_periodic_inventory
from functions.DatabaseManager import DatabaseManager

db_manager = DatabaseManager()

if __name__ == '__main__':
    start_periodic_inventory()

    # Starte Flask-App
    app.app.run(host='0.0.0.0',
                port=5000,
                debug=True
                )