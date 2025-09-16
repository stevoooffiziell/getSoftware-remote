from app import app
from scheduler_service import start_periodic_inventory
from DatabaseManager import DatabaseManager

db_manager = DatabaseManager()

if __name__ == '__main__':
    start_periodic_inventory()

    # Starte Flask-App
    app.run(host='0.0.0.0', port=5000, debug=False)