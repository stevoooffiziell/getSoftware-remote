# -*- coding: utf-8 -*-
import logging
import os

import pyodbc
from flask import Flask, render_template, request, jsonify

from DatabaseManager import DatabaseManager
from globals import service_active
from scheduler_service import run_inventory
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

LOG_DIR = 'logs'
os.makedirs(LOG_DIR, exist_ok=True)

# Logger für Applikationslogs
logging.basicConfig(
    filename=os.path.join(LOG_DIR, 'app.log'),
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)




def get_db_connection():
    """Stellt eine sichere Verbindung zur MS SQL-Datenbank her"""

    host = DatabaseManager().host
    user = DatabaseManager().user
    db = DatabaseManager().db
    pwd = DatabaseManager().pwd
    driver = DatabaseManager().driver

    connection_str = (
            f"DRIVER=" + "{" + f"{driver}" + "}" + f";"
            f"SERVER={host},1433;"
            f"DATABASE={db};"
            f"UID={user};"
            f"PWD={pwd};"
            f"TrustServerCertificate=yes;"
            f"Authentication=SqlPassword;"
    )

    try:
        conn = pyodbc.connect(connection_str)
        logging.info("Datenbankverbindung erfolgreich hergestellt")
        return conn
    except Exception as e:
        logging.error(f"Datenbankverbindungsfehler: {str(e)}")
        raise

# Willkommensnachricht nur einmal beim Start anzeigen
if os.environ.get('WERKZEUG_RUN_MAIN') != 'true' or not hasattr(app, 'welcome_shown'):
    print("\n" + "="*80)
    print("Software Inventory Service gestartet")
    print(f"Startzeit: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*80 + "\n")
    app.welcome_shown = True

def get_scheduler():
    from scheduler_service import scheduler
    return scheduler


@app.route('/')
def dashboard():
    return render_template('dashboard.html')

def log_request(action):
    """Loggt API-Anfragen in einer Datei pro Tag"""
    today = datetime.now().strftime("%Y-%m-%d")
    log_file = os.path.join(LOG_DIR, f"{today}.log")

    log_entry = f"[{datetime.now()}] {action} {request.remote_addr} {request.url}\n"

    try:
        with open(log_file, "a") as f:
            f.write(log_entry)
    except Exception as e:
        logging.error(f"Log-Schreibfehler: {str(e)}")

@app.route('/inventory', methods=['GET'])
def get_inventory():
    global conn
    log_request("INVENTORY_ACCESS")

    # Sortierparameter verarbeiten
    sort_by = request.args.get('sort', 'hostname')
    valid_columns = ['hostname', 'id', 'software_name', 'last_updated']

    # Sicher gegen SQL-Injection
    if sort_by.lower() not in valid_columns:
        sort_by = 'hostname'

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Parameterisiertes Query mit Whitelisting
        query = f"SELECT * FROM software_inventory ORDER BY {sort_by}"
        cursor.execute(query)

        # Ergebnisse in Dictionary konvertieren
        columns = [column[0] for column in cursor.description]
        results = [
            dict(zip(columns, row))
            for row in cursor.fetchall()
        ]

        return jsonify(results)

    except Exception as e:
        logging.error(f"Inventory-Abfragefehler: {str(e)}")
        return jsonify({"error": str(e)}), 500
    finally:
        if 'conn' in locals():
            conn.close()

@app.route('/stop-service', methods=['POST'])
def stop_service():
    service_active.clear()
    return jsonify({"status": "stopping"})

@app.route('/start-service', methods=['POST'])
def start_service():
    service_active.set()
    return jsonify({"status": "started"})

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


@app.route('/logs', methods=['GET'])
def show_logs():
    log_request("LOGS_ACCESS")

    requested_log = request.args.get('file')
    log_files = sorted([
        f for f in os.listdir(LOG_DIR)
        if f.endswith('.log') and not f.startswith('app')
    ])

    if requested_log:
        # Sicherheitsprüfung: Nur Log-Dateien aus dem Verzeichnis
        if requested_log not in log_files:
            return "Log-Datei nicht gefunden", 404

        try:
            with open(os.path.join(LOG_DIR, requested_log), 'r') as f:
                content = f.read()
            return f"<pre>{content}</pre>"
        except Exception as e:
            logging.error(f"Log-Lesefehler: {str(e)}")
            return "Fehler beim Lesen der Log-Datei", 500

    # HTML für Log-Auswahl
    return render_template('logs.html')

@app.route('/status')
def service_status():
    """Gibt den aktuellen Dienststatus zurück"""
    inventory_running = any(t.name == "inventory_thread" for t in threading.enumerate())

    return render_template("status.html",
                           inventory_running=inventory_running,
                           service_active=service_active.is_set())

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


if __name__ == '__main__':
    # Create required directories
    os.makedirs("json", exist_ok=True)
    os.makedirs("logs", exist_ok=True)
    os.makedirs("csv", exist_ok=True)

    # Disable the reloader for stable operation
    app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=False)
