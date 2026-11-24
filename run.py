# -*- coding: utf-8 -*-
from app.app import app, PORT
from app.scheduler_service import start_periodic_inventory

if __name__ == '__main__':
    # Zeitgesteuerte Inventur
    start_periodic_inventory()

    app.run(host='0.0.0.0', port=PORT, debug=False)
