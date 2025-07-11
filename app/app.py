# -*- coding: utf-8 -*-
import logging
import os
import time
import threading
import socket
import platform
import flask
import pyodbc
from datetime import datetime, timedelta
from flask import Flask, render_template, request, jsonify, redirect, url_for, render_template_string
from flask_httpauth import HTTPBasicAuth
from werkzeug.security import generate_password_hash, check_password_hash

from DatabaseManager import DatabaseManager
from scheduler_service import periodic_inventory
from globals import service_active

app = Flask(__name__, template_folder='templates')
auth = HTTPBasicAuth()

# Konfiguration für Basic Auth
users = {
    "admin": generate_password_hash(os.getenv('ADMIN_PASSWORD', 'default-secret'))
}


@auth.verify_password
def verify_password(username, password):
    if username in users and check_password_hash(users.get(username), password):
        return username
    return None


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

# Systeminformationen
system_info = {
    'hostname': socket.gethostname(),
    'ip_address': socket.gethostbyname(socket.gethostname()),
    'os': platform.platform(),
    'python_version': platform.python_version(),
    'flask_version': flask.__version__,
    'start_time': datetime.now()
}

# Willkommensnachricht nur einmal beim Start anzeigen
if os.environ.get('WERKZEUG_RUN_MAIN') != 'true' or not hasattr(app, 'welcome_shown'):
    print("\n" + "=" * 80)
    print("Software Inventory Service gestartet")
    print(f"Startzeit: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80 + "\n")
    app.welcome_shown = True


@app.route('/')
def dashboard():
    """Haupt-Dashboard-Seite"""
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
@auth.login_required
def get_inventory():
    """Zeigt die Software-Inventarliste an"""
    log_request("INVENTORY_ACCESS")

    try:
        conn = db_manager.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM software_inventory ORDER BY hostname, name")

        # Ergebnisse in Dictionary konvertieren
        columns = [column[0] for column in cursor.description]
        inventory = [
            dict(zip(columns, row))
            for row in cursor.fetchall()
        ]

        return render_template('inventory.html', inventory=inventory)

    except Exception as e:
        logging.error(f"Inventory-Abfragefehler: {str(e)}")
        return render_template('error.html', error=str(e)), 500


@app.route('/run-inventory', methods=['POST'])
@auth.login_required
def trigger_inventory():
    """Startet den Inventurprozess manuell"""
    if not service_active.is_set():
        return jsonify({
            "status": "error",
            "message": "Service ist deaktiviert"
        }), 403

    def inventory_task():
        try:
            execution_logs["current"] = f"{datetime.now()} - Starting manual inventory...\n"
            execution_logs["last_update"] = datetime.now()

            # Hauptinventurprozess ausführen
            from testMain import main as run_inventory
            run_inventory()

            # Letzten Lauf speichern
            db_manager.set_metadata("last_run", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

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

    # Prüfen, ob bereits ein Inventurlauf aktiv ist
    if any(t.name == "manual_inventory_thread" for t in threading.enumerate()):
        return jsonify({
            "status": "error",
            "message": "Inventory is already running"
        }), 429

    # Neuen Thread starten
    thread = threading.Thread(target=inventory_task, name="manual_inventory_thread")
    thread.daemon = True
    thread.start()

    return jsonify({"status": "started"})


@app.route('/stop-service', methods=['POST'])
@auth.login_required
def stop_service():
    """Deaktiviert den Service"""
    service_active.clear()
    logging.warning("Service wurde deaktiviert")
    return jsonify({"status": "stopping"})


@app.route('/start-service', methods=['POST'])
@auth.login_required
def start_service():
    """Aktiviert den Service"""
    service_active.set()
    logging.info("Service wurde aktiviert")
    return jsonify({"status": "started"})


@app.route('/logs', methods=['GET'])
@auth.login_required
def show_logs():
    """Zeigt Logdateien an"""
    log_request("LOGS_ACCESS")

    requested_log = request.args.get('file')
    log_files = sorted([
        f for f in os.listdir(LOG_DIR)
        if f.endswith('.log') and not f.startswith('app')
    ])

    if requested_log:
        # Sicherheitsprüfung: Nur Log-Dateien aus dem Verzeichnis
        if requested_log not in log_files and requested_log != 'app.log':
            return render_template('error.html', error="Log-Datei nicht gefunden"), 404

        try:
            with open(os.path.join(LOG_DIR, requested_log), 'r') as f:
                content = f.read()
            return render_template('log_viewer.html', log_content=content, log_file=requested_log)
        except Exception as e:
            logging.error(f"Log-Lesefehler: {str(e)}")
            return render_template('error.html', error="Fehler beim Lesen der Log-Datei"), 500

    return render_template('logs.html', logs=log_files)


@app.route('/status')
def service_status():
    """Gibt den aktuellen Dienststatus zurück"""
    inventory_running = any(t.name == "manual_inventory_thread" for t in threading.enumerate())

    # Uptime berechnen
    uptime = datetime.now() - system_info['start_time']
    days = uptime.days
    hours, remainder = divmod(uptime.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    uptime_str = f"{days} Tage, {hours} Stunden"

    # Letzten Lauf abrufen
    last_run = db_manager.get_metadata("last_run") or "Noch nicht durchgeführt"
    interval_weeks = int(db_manager.get_metadata("interval_weeks") or 2)

    # Nächsten Lauf berechnen
    next_run = "Unbekannt"
    if last_run != "Noch nicht durchgeführt":
        last_run_dt = datetime.strptime(last_run, "%Y-%m-%d %H:%M:%S")
        next_run_dt = last_run_dt + timedelta(weeks=interval_weeks)
        next_run = next_run_dt.strftime("%Y-%m-%d %H:%M")

    return render_template("status.html",
                           inventory_running=inventory_running,
                           service_active=service_active.is_set(),
                           system_info=system_info,
                           uptime=uptime_str,
                           last_restart=system_info['start_time'].strftime("%Y-%m-%d %H:%M:%S"),
                           last_run=last_run,
                           next_run=next_run,
                           interval_weeks=interval_weeks)


@app.route('/settings', methods=['GET', 'POST'])
@auth.login_required
def settings():
    """Einstellungsseite für Anpassungen"""
    interval_weeks = int(db_manager.get_metadata("interval_weeks") or 2)

    if request.method == 'POST':
        try:
            new_interval = int(request.form.get('interval', interval_weeks))
            if new_interval < 1:
                raise ValueError("Intervall muss mindestens 1 Woche betragen")

            db_manager.set_metadata("interval_weeks", str(new_interval))
            return render_template('settings.html',
                                   interval=new_interval,
                                   message=f"Intervall auf {new_interval} Wochen gesetzt")
        except Exception as e:
            return render_template('settings.html',
                                   interval=interval_weeks,
                                   error=f"Ungültiges Intervall: {str(e)}")

    return render_template('settings.html', interval=interval_weeks)


@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404


@app.errorhandler(500)
def internal_server_error(e):
    return render_template('500.html'), 500


if __name__ == '__main__':
    # Create required directories
    os.makedirs("json", exist_ok=True)
    os.makedirs("logs", exist_ok=True)
    os.makedirs("csv", exist_ok=True)

    # Metadaten initialisieren
    if not db_manager.get_metadata("interval_weeks"):
        db_manager.set_metadata("interval_weeks", "2")

    # Starte periodischen Inventur-Thread
    interval_weeks = int(db_manager.get_metadata("interval_weeks") or 2)
    inventory_thread = threading.Thread(
        target=periodic_inventory,
        args=(interval_weeks,),
        name="periodic_inventory",
        daemon=True
    )
    inventory_thread.start()

    # Starte Flask-App
    app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=False)