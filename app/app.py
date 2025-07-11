# -*- coding: utf-8 -*-
import os
import time

from flask import Flask, render_template, request, jsonify, redirect, url_for

from DatabaseManager import DatabaseManager
from scheduler_service import scheduler, run_inventory
from datetime import datetime
import threading

app = Flask(__name__, template_folder='templates')

# Globaler Singleton für DatabaseManager
db_manager = DatabaseManager()

# In-Memory-Log-Speicher
execution_logs = {
    "current": "",
    "history": [],
    "last_update": datetime.now()
}

# Willkommensnachricht nur einmal beim Start anzeigen
if os.environ.get('WERKZEUG_RUN_MAIN') != 'true' or not hasattr(app, 'welcome_shown'):
    print("\n" + "="*80)
    print("Software Inventory Service gestartet")
    print(f"Startzeit: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*80 + "\n")
    app.welcome_shown = True


@app.route('/')
def dashboard():
    return render_template('dashboard.html')


@app.route('/run-inventory', methods=['POST'])
def trigger_inventory():
    """
    Startet den Inventurprozess manuell

    :return: tuple[Response, int] | Response
    """

    def inventory_task():
        try:
            execution_logs["current"] = f"{datetime.now()} - Starting manual inventory...\n"
            execution_logs["last_update"] = datetime.now()

            # Hauptinventurprozess ausführen
            time.sleep(5)
            run_inventory()

            # Erfolgsmeldung
            execution_logs["current"] += f"\n{datetime.now()} - Inventory completed successfully"
            execution_logs["history"].append({
                "timestamp": datetime.now().isoformat(),
                "log": execution_logs["current"],
                "status": "success"
            })

        except Exception as e:
            error_msg = f"{datetime.now()} - Inventory error: {str(e)}"
            execution_logs["current"] += "\n" + error_msg
            execution_logs["history"].append({
                "timestamp": datetime.now().isoformat(),
                "log": execution_logs["current"],
                "status": "error"
            })

    # Check if there's an existing inventory thread
    # Prüfen, ob bereits ein Inventurlauf aktiv ist
    if any(t.name == "inventory_thread" for t in threading.enumerate()):
        return jsonify({
            "status": "error",
            "message": "Inventory is already running"
        }), 429

        # Neuen Thread starten
    thread = threading.Thread(target=inventory_task, name="inventory_thread")
    thread.daemon = True
    thread.start()

    return jsonify({"status": "started"})


@app.route('/logs')
def get_logs():
    """
    returns latest logs

    :return:
    """
    return jsonify({
        "current": execution_logs["current"],
        "history": execution_logs["history"][-50:],
        "last_update": execution_logs["last_update"].isoformat()
    })


@app.route('/settings', methods=['GET', 'POST'])
def settings():
    """
    settings landingpage for adjustments

    :return:
    """
    if request.method == 'POST':
        try:
            new_interval = int(request.form.get('interval', 2))
            # Hier Intervall aktualisieren
            return jsonify({
                "status": "success",
                "message": f"Interval set to {new_interval} weeks"
            })
        except Exception as e:
            return jsonify({
                "status": "error",
                "message": f"Invalid interval: {str(e)}"
            }), 400

    return render_template('settings.html', interval=2)


@app.route('/status')
def service_status():
    """Gibt den aktuellen Dienststatus zurück"""
    print("Hallo")
    inventory_running = any(t.name == "inventory_thread" for t in threading.enumerate())
    print("Hallo2")

    return render_template("status.html")

if __name__ == '__main__':
    # Create required directories
    os.makedirs("json", exist_ok=True)
    os.makedirs("logs", exist_ok=True)
    os.makedirs("csv", exist_ok=True)

    # Disable the reloader for stable operation
    app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=False)
