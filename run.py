# -*- coding: utf-8 -*-
from app.app import app, PORT

if __name__ == '__main__':
    # Zeitgesteuerte Inventur aktivieren:
    # from app.scheduler_service import start_periodic_inventory
    # start_periodic_inventory()

    app.run(host='0.0.0.0', port=PORT, debug=False)
