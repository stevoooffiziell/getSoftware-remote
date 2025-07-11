# -*- coding: utf-8 -*-
import logging
import os
import threading
import socket
import platform
from datetime import datetime

import flask
import pyodbc
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


def get_db_connection():
    """Stellt eine sichere Verbindung zur MS SQL-Datenbank her"""
    config = {
        'host': db_manager.host,
        'user': db_manager.user,
        'pwd': db_manager.pwd,
        'db': db_manager.db,
        'driver': db_manager.driver
    }

    connection_str = (
        f"DRIVER={{{config['driver']}}};"
        f"SERVER={config['host']},1433;"
        f"DATABASE={config['db']};"
        f"UID={config['user']};"
        f"PWD={config['pwd']};"
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
    if any(t.name == "inventory_thread" for t in threading.enumerate()):
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
    log_request("LOGS_ACCESS")

    requested_log = request.args.get('file')
    log_files = sorted([
        f for f in os.listdir(LOG_DIR)
        if f.endswith('.log') and not f.startswith('app')
    ])

    if requested_log:
        # Sicherheitsprüfung: Nur Log-Dateien aus dem Verzeichnis
        if requested_log not in log_files and requested_log != 'app.log':
            return "Log-Datei nicht gefunden", 404

        try:
            with open(os.path.join(LOG_DIR, requested_log), 'r') as f:
                content = f.read()
            return f"<pre>{content}</pre>"
        except Exception as e:
            logging.error(f"Log-Lesefehler: {str(e)}")
            return "Fehler beim Lesen der Log-Datei", 500

    # HTML für Log-Auswahl
    return render_template_string('''
        <h1>Verfügbare Logdateien</h1>
        <ul>
            {% for log in logs %}
                <li><a href="/logs?file={{ log }}">{{ log }}</a></li>
            {% endfor %}
        </ul>
        <p>Anwendungslogs: <a href="/logs?file=app.log">app.log</a></p>
    ''', logs=log_files)


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

    return render_template("status.html",
                           inventory_running=inventory_running,
                           service_active=service_active.is_set(),
                           system_info=system_info,
                           uptime=uptime_str,
                           last_restart=system_info['start_time'].strftime("%Y-%m-%d %H:%M:%S"))


@app.route('/settings', methods=['GET', 'POST'])
@auth.login_required
def settings():
    """Einstellungsseite für Anpassungen"""
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

    # Starte periodischen Inventur-Thread
    inventory_thread = threading.Thread(
        target=periodic_inventory,
        args=(2,),
        name="periodic_inventory",
        daemon=True
    )
    inventory_thread.start()

    # Starte Flask-App
    app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=False)