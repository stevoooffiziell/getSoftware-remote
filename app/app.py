# -*- coding: utf-8 -*-

import logging
import os
import platform
import secrets
import socket
import threading
from datetime import datetime, timedelta

import flask
import pyodbc
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, session
from flask.cli import load_dotenv
from flask_executor import Executor
from flask_httpauth import HTTPBasicAuth

import vars.global_vars as global_vars
from functions.DatabaseManager import DatabaseManager, LOG_DIR
from functions.pwsh_processor import run_inventory_cycle
from secret.user_management import user_auth

app = Flask(__name__, template_folder='templates', static_folder="static")

load_dotenv()

# Ohne SECRET_KEY in der Umgebung/.env wird ein zufälliger Schlüssel erzeugt
# (Sitzungen sind dann nach einem Neustart ungültig).
app.secret_key = os.environ.get('SECRET_KEY') or secrets.token_hex(32)

app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=1)
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_pre_ping': True,
    'pool_recycle': 300,
}

# flask_cors.CORS(app)
auth = HTTPBasicAuth()
executor = Executor(app)

# In-Memory-Log-Speicher
execution_logs = {
    "current": "",
    "history": [],
    "last_update": datetime.now()
}

# Globaler Singleton für DatabaseManager
db_manager = DatabaseManager()


# log directory
os.makedirs(LOG_DIR, exist_ok=True)

DATE_FMT_DE = "%d.%m.%Y %H:%M:%S"
DATE_FMT_ISO = "%Y-%m-%d %H:%M:%S"
INVENTORY_THREAD_NAME = "manual_inventory_thread"

# Logger für Applikationslogs
logging.basicConfig(filename=os.path.join(LOG_DIR, f'{db_manager.get_timestamp("dmy")}-app.log'), level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')

def format_dt(value, fmt, default=None):
    """Formatiert ein ``datetime``; liefert ``default`` für fehlende Werte."""
    return value.strftime(fmt) if isinstance(value, datetime) else default


def sync_service_status():
    """Übernimmt den Service-Status aus der Datenbank und gibt ihn zurück."""
    service_active_db = db_manager.get_metadata("service_active")
    if service_active_db == 1:
        global_vars.service_active.set()
    else:
        global_vars.service_active.clear()
    return service_active_db


# Systeminformationen
system_info = {
    'hostname': socket.gethostname(),
    'ip_address': socket.gethostbyname(socket.gethostname()),
    'os': platform.platform(),
    'python_version': platform.python_version(),
    'flask_version': flask.__version__,
    'start_time': datetime.now()
}

try:
    print(f"Service status synchronized from database: {'Active' if sync_service_status() == 1 else 'Inactive'}")
except Exception as e:
    print(f"Error synchronizing service status: {e}")

port = 5000  #hell no, go away...

# Willkommensnachricht nur einmal beim Start anzeigen
if os.environ.get('WERKZEUG_RUN_MAIN') != 'true' or not hasattr(app, 'welcome_shown'):
    print("\n" + "=" * 80)
    print("Software Inventory Service gestartet")
    print(f"Startzeit: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Website ist zugänglich über {system_info['ip_address']}:{port}")
    print("=" * 80 + "\n")
    app.welcome_shown = True

@auth.verify_password
def verify_password(username, password):
    if user_auth(username, password):
        return username
    return None


# Login-Erforderlich für alle Routen
@app.before_request
def require_login():
    allowed_routes = ['login', 'static']
    if request.endpoint in allowed_routes:
        return None

    if 'username' not in session:
        return redirect(url_for('login'))

    session['last_activity'] = datetime.now().strftime(DATE_FMT_DE)
    return None


def run_and_record():
    try:
        run_inventory_cycle(db_manager)
    except Exception as e:
        logging.error(f"Error during manual inventory: {str(e)}")


def launch_inventory():
    """Startet die Inventur im Hintergrund, sofern nicht bereits eine läuft."""
    if global_vars.begin_run():
        threading.Thread(target=run_and_record, name=INVENTORY_THREAD_NAME, daemon=True).start()
    return redirect(url_for('inventory_progress'))


@app.route('/')
def dashboard():
    """Haupt-Dashboard-Seite"""
    # Alle Kennzahlen in einer einzigen Abfrage statt fünf Tabellenscans
    _, rows = db_manager.fetch_all(
        f"SELECT COUNT(DISTINCT hostname), COUNT(DISTINCT name), COUNT(name), COUNT(DISTINCT publisher) "
        f"FROM dbo.{db_manager.table_name}")
    count_hosts, count_sw, count_sw_all, count_publisher = rows[0]

    return render_template('dashboard.html',
                           count_hosts=count_hosts,
                           count_sw_all=count_sw_all,
                           count_sw=count_sw,
                           count_publisher=count_publisher,
                           last_run=get_last_run(),
                           next_run=format_dt(db_manager.get_metadata("next_inventory_run"), DATE_FMT_ISO, "-"))


def get_last_run():
    return format_dt(db_manager.get_metadata("last_inventory_start"), DATE_FMT_DE, "Noch nicht ausgeführt")


def log_request(action):
    """Loggt API-Anfragen in einer Datei pro Tag"""
    today = datetime.now().strftime("%Y-%m-%d")
    log_file = os.path.join(LOG_DIR, f"{today}.log")

    log_entry = f"[{datetime.now()}] {action} {request.remote_addr} {request.url}\n"

    try:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(log_entry)
    except Exception as e:
        logging.error(f"Log-Schreibfehler: {str(e)}")


@app.route('/start-inventory')
def start_inventory():
    return launch_inventory()


@app.route('/inventory-progress')
def inventory_progress():
    with global_vars.processed_hosts_lock:
        processed = global_vars.processed_hosts
        total = global_vars.total_hosts

    percentage = min(100, round(processed / total * 100)) if total else 0

    return render_template('process.html', percentage=percentage,
                           processed_hosts=processed,
                           remaining_systems=max(total - processed, 0),
                           total_hosts=total)


@app.route('/inventory-progress-data')
def progress_data():
    with global_vars.processed_hosts_lock:
        return jsonify({
            'is_running': global_vars.is_running,
            'total_hosts': global_vars.total_hosts,
            'processed_hosts': global_vars.processed_hosts,
            'start_time': format_dt(global_vars.inventory_start_time, DATE_FMT_ISO),
            'last_run': format_dt(global_vars.last_run_time, DATE_FMT_ISO)
        })


@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'username' in session:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        username = request.form.get('username', '')
        password = request.form.get('password', '')

        if not username or not password:
            flash('Bitte füllen Sie beide Felder aus', 'error')
            return render_template('login.html')

        # Direkte Nutzung von user_auth zur Authentifizierung
        if user_auth(username, password):
            session['username'] = username
            session['login_time'] = session['last_activity'] = datetime.now().strftime(DATE_FMT_DE)
            flash('Sie wurden erfolgreich angemeldet', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Ungültige Anmeldedaten', 'error')
            return render_template('login.html')
    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    flash('Du wurdest erfolgreich abgemeldet')
    return redirect(url_for('login'))


@app.route('/inventory', methods=['GET'])
def get_inventory():
    """Zeigt die Software-Inventarliste an"""
    log_request("INVENTORY_ACCESS")

    columns, rows = db_manager.fetch_all(f"SELECT * FROM dbo.{db_manager.table_name}")
    inventory = [dict(zip(columns, row)) for row in rows]

    return render_template('inventory.html', inventory=inventory)


@app.route('/run-inventory', methods=['GET', 'POST'])
@auth.login_required
def run_inventory():
    if not global_vars.service_active.is_set():
        return render_template("403.html"), 403

    return launch_inventory()


@app.route('/stop-service', methods=['POST'])
@auth.login_required
def stop_service():
    # Zuerst Datenbank, dann global_vars
    if not db_manager.set_metadata("service_active", 0):
        return jsonify({"status": "error", "message": "Database update failed"}), 500
    global_vars.service_active.clear()

    logging.warning("Service wurde deaktiviert")
    return jsonify({"status": "stopping"})


@app.route('/start-service', methods=['POST'])
@auth.login_required
def start_service():
    # Zuerst Datenbank, dann global_vars
    if not db_manager.set_metadata("service_active", 1):
        return jsonify({"status": "error", "message": "Database update failed"}), 500
    global_vars.service_active.set()

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
            with open(os.path.join(LOG_DIR, requested_log), 'r', encoding='utf-8', errors='replace') as f:
                content = f.read()
            return render_template('log_viewer.html', log_content=content, log_file=requested_log)
        except Exception as e:
            logging.error(f"Log-Lesefehler: {str(e)}")
            return render_template('error.html', error="Fehler beim Lesen der Log-Datei"), 500

    return render_template('logs.html', logs=log_files)


@app.route('/status')
def service_status():
    """
    Routes to the status page. Which provides important data.\n
    ``inventory_running`` checks if there are any active threads, if so it will pass an integer to the corresponding HTML\n
    ``uptime`` calculates the uptime of the service not the system itself\n
    ``days, hours, minutes, remainder`` are self explaining\n
    ``connection`` is used to check if the connection to the database is still active\n\
    ``last_run`` calls the ``get_last_run()`` function\n
    ``last_run_value, status_interval_weeks, service_active_int, next_run`` retrieve their values from the given database if configured.\n
    ``last_run_dt, next_run_dt, next_run`` converts the date object into a compatible form to calculate the next actual run\n

    :return flask.render_template:
    """
    # Ein Durchlauf über die Threadliste für beide Kennzahlen
    threads = sum(1 for t in threading.enumerate() if t.name.startswith("manual"))
    inventory_running = global_vars.is_running

    # Uptime berechnen
    uptime = datetime.now() - system_info['start_time']
    hours, remainder = divmod(uptime.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    uptime_str = f"{uptime.days} Tag(e), {hours} Stunde(n), {minutes} Minute(n), {seconds} Sekunde(n)"

    service_active_db = sync_service_status()

    return render_template("status.html",
                           inventory_running=inventory_running,
                           service_active=service_active_db,  # Verwende den DB-Wert
                           system_info=system_info,
                           uptime=uptime_str,
                           last_restart=system_info['start_time'].strftime(DATE_FMT_ISO),
                           last_run=get_last_run(),
                           interval_weeks=int(db_manager.get_metadata("interval_weeks") or 0),
                           threads=threads,
                           connection=db_manager.conn is not None,
                           next_run=format_dt(db_manager.get_metadata("next_inventory_run"), DATE_FMT_DE, "-"))


@app.route('/account')
def account():
    """Kontoübersicht für den angemeldeten Benutzer"""

    # Hier könnten man zusätzliche Benutzerinformationen aus einer Datenbank abrufen
    username = session['username']

    return render_template('account.html', username=username)


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


@app.errorhandler(401)
def not_authorized(e):
    return render_template('401.html', e=e), 401


@app.errorhandler(403)
def forbidden(e):
    return render_template('403.html', e=e), 403


@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html', e=e), 404


@app.errorhandler(500)
def internal_server_error(e):
    return render_template('500.html', e=e), 500


@app.route('/test-db')
def test_db():
    """Testet die Datenbankverbindung und Metadata-Funktionen"""
    try:
        # Teste get_metadata
        service_active = db_manager.get_metadata("service_active")
        print(f"DEBUG: Current service_active from DB: {service_active} (Type: {type(service_active)})")

        # Teste set_metadata
        test_value = 1 if service_active == 0 else 0
        print(f"DEBUG: Testing set_metadata with value: {test_value}")
        success = db_manager.set_metadata("service_active", test_value)

        # Überprüfe das Ergebnis
        new_value = db_manager.get_metadata("service_active")
        print(f"DEBUG: New service_active from DB: {new_value}")

        return jsonify({
            "success": success,
            "old_value": service_active,
            "new_value": new_value,
            "test_value": test_value
        })
    except Exception as err:
        return jsonify({"error": str(err)}), 500


@app.route('/check-drivers')
def check_drivers():
    """Überprüft verfügbare ODBC-Treiber"""
    try:
        drivers = pyodbc.drivers()
        return jsonify({
            "available_drivers": drivers,
            "current_database_uri": app.config['SQLALCHEMY_DATABASE_URI']
        })
    except Exception as e:
        return jsonify({"error": str(e)})

@app.route('/reset-database')
def reset_database():
    return jsonify({"error": "Not implemented"}), 501
