# -*- coding: utf-8 -*-
import json
import logging
import os
import threading
import socket
import platform
from threading import Thread

import flask
from datetime import datetime, timedelta
from flask import Flask, render_template, request, jsonify
from flask_httpauth import HTTPBasicAuth
from flask_executor import Executor
from werkzeug.security import generate_password_hash, check_password_hash

from DatabaseManager import DatabaseManager
from globals import service_active

app = Flask(__name__, template_folder='templates')
auth = HTTPBasicAuth()

executor = Executor(app)

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

def run_and_record():
    try:
        from testMain import main as inventory_main
        inventory_main()
        # Endzeit speichern
        end_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        db_manager.set_metadata("last_inventory_end", end_time)
    except Exception as e:
        logging.error(f"Error during manual inventory: {str(e)}")

def get_last_run():
    conn = db_manager.connect_db()
    cursor = conn.cursor()
    cursor.execute("SELECT last_run from dbo.service_metadata")

    date_last_run = cursor.fetchall()
    dt = datetime.strptime(str(date_last_run[0][0]), "%Y-%m-%d %H:%M:%S")
    de_format = dt.strftime("%d.%m.%Y %H:%M:%S")

    if de_format == "01.01.1900 00:00:00":
        de_format = "Noch nicht ausgeführt"

    return de_format


# In-Memory-Log-Speicher
execution_logs = {
    "current": "",
    "history": [],
    "last_update": datetime.now()
}

LOG_DIR = 'logs'
os.makedirs(LOG_DIR, exist_ok=True)

# Logger für Applikationslogs
logging.basicConfig(filename=os.path.join(LOG_DIR, 'app.log'),level=logging.INFO,format='%(asctime)s - %(levelname)s - %(message)s')

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
    def get_distinct_number_hosts():
        conn = db_manager.connect_db()
        cursor = conn.cursor()
        cursor.execute(f"SELECT COUNT(DISTINCT hostname) from dbo.{db_manager.table_name}")

        count = cursor.fetchall()
        return count[0][0]

    def get_distinct_number_software():
        conn = db_manager.connect_db()
        cursor = conn.cursor()
        cursor.execute(f"SELECT COUNT(DISTINCT name) from dbo.{db_manager.table_name}")
        count = cursor.fetchall()
        cursor.execute(f"SELECT COUNT(name) from dbo.{db_manager.table_name}")
        count_all = cursor.fetchall()

        return count[0][0], count_all[0][0]

    def get_distinct_number_publisher():
        conn = db_manager.connect_db()
        cursor = conn.cursor()
        cursor.execute(f"SELECT COUNT(DISTINCT publisher) from dbo.{db_manager.table_name}")

        count = cursor.fetchall()
        return count[0][0]

    last_run = get_last_run()
    count_hosts = get_distinct_number_hosts()
    count_sw = get_distinct_number_software()[0]
    count_sw_all = get_distinct_number_software()[1]
    count_publisher = get_distinct_number_publisher()

    return render_template('dashboard.html',
                           count_hosts=count_hosts,
                           count_sw_all=count_sw_all,
                           count_sw=count_sw,
                           count_publisher=count_publisher,
                           last_run=last_run)


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
    """Zeigt die Software-Inventarliste an"""
    log_request("INVENTORY_ACCESS")
    software_inventory = "software_inventory"

    def get_data_from_database():
        conn = db_manager.connect_db()
        cursor = conn.cursor()

        cursor.execute(f"SELECT * FROM {db_manager.table_name}")
        columns = [column[0] for column in cursor.description]

        cursor.execute(f"SELECT * FROM {db_manager.table_name}")
        rows = cursor.fetchall()

        inventory = [dict(zip(columns, row)) for row in rows]
        return inventory

    data = get_data_from_database()

    return render_template('inventory.html', inventory=data)


@app.route('/run-inventory', methods=['GET', 'POST'])
@auth.login_required
def run_inventory():
    if not service_active.is_set():
        return jsonify({"status": "error", "message": "Service disabled"}), 403

    # Alle aktiven manuellen Threads ermitteln
    if any(t.name == "manual_inventory_thread" for t in threading.enumerate()):
        return jsonify({"status": "error", "message": "Inventory is already running"}), 429

    # Startzeit speichern
    start_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    db_manager.set_metadata("last_inventory_start", start_time)

    man_thread = threading.Thread(
        target=run_and_record,
        name="manual_inventory_thread",
        daemon=True)
    man_thread.start()
    print(man_thread.is_alive(), man_thread.name)

    return jsonify({"status": "started", "message": "Inventory process started"})


@app.route('/stop-service', methods=['POST'])
@auth.login_required
def stop_service():
    service_active.clear()
    db_manager.set_metadata("service_active", "0")
    logging.warning("Service wurde deaktiviert")

    return jsonify({"status": "stopping"})


@app.route('/start-service', methods=['POST'])
@auth.login_required
def start_service():
    service_active.set()
    db_manager.set_metadata("service_active", "1")

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

    # if inventory_running:
    #     db_manager.set_metadata("last_run", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    # Uptime berechnen
    uptime = datetime.now() - system_info['start_time']
    days = uptime.days
    hours, remainder = divmod(uptime.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    uptime_str = f"{days} Tage, {hours} Stunden"
    connection = False

    if db_manager.conn is not None :
        connection = True

    last_run = get_last_run()

    last_run_value = db_manager.get_metadata("last_run")  # Raw-Wert aus DB
    status_interval_weeks = int(db_manager.get_metadata("interval_weeks")[0])
    service_active_int = int(db_manager.get_metadata("service_active")[0])

    # Nächsten Lauf NUR berechnen, wenn ein gültiges Datum existiert
    next_run = db_manager.get_metadata("next_run")[0]  # Default-Wert
    if next_run == "None":
        try:
            last_run_dt = datetime.strptime(last_run_value, "%Y-%m-%d %H:%M:%S")
            next_run_dt = last_run_dt + timedelta(weeks=status_interval_weeks)
            next_run = next_run_dt.strftime("%d.%m.%Y %H:%M:%S")
        except (ValueError, TypeError):
            next_run = "Ungültiges Datumsformat"


    def get_active_man_threads_count():
        return sum(1 for t in threading.enumerate() if t.name.startswith("manual"))

    threads = get_active_man_threads_count()
    print(threads)

    return render_template("status.html",
                           inventory_running=inventory_running,
                           service_active=service_active_int,
                           system_info=system_info,
                           uptime=uptime_str,
                           last_restart=system_info['start_time'].strftime("%Y-%m-%d %H:%M:%S"),
                           last_run=last_run,
                           next_run=next_run,
                           interval_weeks=status_interval_weeks,
                           threads=threads,
                           connection=connection)


@app.route('/settings', methods=['GET', 'POST'])
@auth.login_required
def settings():
    """Einstellungsseite für Anpassungen"""
    interval_weeks = db_manager.get_metadata("interval_weeks")

    if request.method == 'POST':
        try:
            new_interval = int(request.form.get('interval', interval_weeks))
            if new_interval < 1:
                raise ValueError("Intervall muss mindestens 1 Woche betragen")

            db_manager.set_metadata("interval_weeks", new_interval)
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
    return render_template('404.html', e=e), 404


@app.errorhandler(500)
def internal_server_error(e):
    return render_template('500.html'), 500
