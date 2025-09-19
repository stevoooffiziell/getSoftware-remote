# -*- coding: utf-8 -*-

import logging
import os
import platform
import socket
import threading
import time
from datetime import datetime, timedelta

import flask
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, session
from flask_executor import Executor
from flask_httpauth import HTTPBasicAuth

import vars.global_vars as global_vars
from functions.DatabaseManager import DatabaseManager
from functions.pwsh_processor import main as host_processor
from secret.user_management import USER_DETAILS_FILEPATH, user_auth
from werkzeug.security import generate_password_hash

app = Flask(__name__, template_folder='templates', static_folder="static")
app.secret_key = os.environ.get('SECRET_KEY', 'default-secret-key-for-sessions')
# flask_cors.CORS(app)
auth = HTTPBasicAuth()
executor = Executor(app)

username_list: list = []

users = {
    "admin": generate_password_hash(os.getenv('ADMIN_PASSWORD', 'default-secret'))
}

def read_user_details():
    with open(USER_DETAILS_FILEPATH, "r") as f:
        for line in f:
            content = line.split(" ")
            if content[0] not in username_list:
                username_list.append(content[0])
                salt = content[1].split("$")[0]
                hash_value = content[1].split("$")[1]
                print(
                    f"{username_list}\n"
                    f"{hash_value}\n"
                    f"{salt}"
                )
            return username_list
    return username_list


# In-Memory-Log-Speicher
execution_logs = {
    "current": "",
    "history": [],
    "last_update": datetime.now()
}

# Globaler Singleton für DatabaseManager
db_manager = DatabaseManager()

# log directory
LOG_DIR = 'logs'
os.makedirs(LOG_DIR, exist_ok=True)

# Logger für Applikationslogs
logging.basicConfig(filename=os.path.join(LOG_DIR, f'{db_manager.get_timestamp("dmy")}-app.log'), level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')

# Systeminformationen
system_info = {
    'hostname': socket.gethostname(),
    'ip_address': socket.gethostbyname(socket.gethostname()),
    'os': platform.platform(),
    'python_version': platform.python_version(),
    'flask_version': flask.__version__,
    'start_time': datetime.now()
}

port = 5000  #hell no, go away...

# Willkommensnachricht nur einmal beim Start anzeigen
if os.environ.get('WERKZEUG_RUN_MAIN') != 'true' or not hasattr(app, 'welcome_shown'):
    print("\n" + "=" * 80)
    print("Software Inventory Service gestartet")
    print(f"Startzeit: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Website ist zugänglich über {system_info['ip_address']}:{port}")
    print("=" * 80 + "\n")
    app.welcome_shown = True




# TODO: Save userdata in database
def init_user_database():
    """
    Initialisiert die Benutzerdatenbank, falls nicht vorhanden
    :return:
    """
    conn = db_manager.connect_db()
    cursor = conn.cursor()

    # Tabelle für Benutzer erstellen, falls nicht vorhanden
    cursor.execute("""
        IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='users' AND xtype='U')
        CREATE TABLE users (
            id INT IDENTITY(1,1) PRIMARY KEY,
            username NVARCHAR(50) UNIQUE NOT NULL,
            password_hash NVARCHAR(255) NOT NULL,
            role NVARCHAR(50) DEFAULT 'user',
            created_at DATETIME DEFAULT GETDATE(),
            last_login DATETIME NULL
        )
    """)

# Beim Start der App aufrufen
init_user_database()


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

    session['last_activity'] = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
    return None


def run_and_record():
    try:
        try:
            db_manager.set_starttime()
            print("Function set_starttime started")
        except Exception as e:
            print(e)

        global start_time
        start_time = time.time()
        with global_vars.processed_hosts_lock:
            global_vars.total_hosts = global_vars.get_total_hosts()
        db_manager.set_starttime()

        host_processor()

        # Endzeit speichern
        end_time = datetime.now()
        db_manager.set_nexttime(start_time)
        calc_next_run()

        # Inventur erfolgreich beendet
        global_vars.last_run_time = end_time.strftime("%Y-%m-%d %H:%M:%S")
        with global_vars.processed_hosts_lock:
            global_vars.last_host_count = global_vars.processed_hosts
            # Stelle sicher, dass processed_hosts gleich total_hosts ist
            if global_vars.processed_hosts < global_vars.total_hosts:
                global_vars.processed_hosts = global_vars.total_hosts
    except Exception as e:
        logging.error(f"Error during manual inventory: {str(e)}")
    finally:
        # Inventurstatus zurücksetzen
        global_vars.is_running = False
        global_vars.inventory_start_time = None


def calc_next_run():
    print("Next run has been calculated")


@app.route('/')
def dashboard():
    """Haupt-Dashboard-Seite"""
    if 'username' not in session:
        return redirect(url_for('login'))

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

    next_run = db_manager.get_metadata("next_inventory_run")
    next_run = next_run.strftime("%Y-%m-%d %H:%M:%S")

    return render_template('dashboard.html',
                           count_hosts=count_hosts,
                           count_sw_all=count_sw_all,
                           count_sw=count_sw,
                           count_publisher=count_publisher,
                           last_run=last_run,
                           next_run=next_run)


def get_last_run():
    conn = db_manager.connect_db()
    cursor = conn.cursor()
    cursor.execute("SELECT last_inventory_start from dbo.service_metadata")
    date_last_run = cursor.fetchall()[0][0]

    if date_last_run != "None":
        dt = datetime.strptime(str(date_last_run), "%Y-%m-%d %H:%M:%S.%f")
        de_format = dt.strftime("%d.%m.%Y %H:%M:%S")
    else:
        de_format = "Noch nicht ausgeführt"
    return de_format

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

@app.route('/start-inventory')
def start_inventory():
    if 'username' not in session:
        return redirect(url_for('login'))
    # Hosts aus CSV zählen
    global_vars.inventory_start_time = datetime.now()
    with global_vars.processed_hosts_lock:
        global_vars.processed_hosts = 0
    global_vars.is_running = True

    # Starte Inventurprozess im Hintergrund
    threading.Thread(target=run_and_record, daemon=True).start()

    return redirect('/inventory-progress')

@app.route('/inventory-progress')
def inventory_progress():
    if 'username' not in session:
        return redirect(url_for('login'))

    def percentage():
        with open('csv\\hosts.csv', 'r') as f:
            for _ in f:
                rows = + 1
        return rows

    def remaining():
        x = global_vars.total_hosts - global_vars.processed_hosts
        return x

    return render_template('process.html', percentage=percentage(),
                           processed_hosts=global_vars.processed_hosts,
                           remaining_systems=remaining(),
                           total_hosts=global_vars.total_hosts)

@app.route('/inventory-progress-data')
def progress_data():
    if 'username' not in session:
        return redirect(url_for('login'))
    print(
        f"Fortschrittsdaten: is_running={global_vars.is_running}, processed={global_vars.processed_hosts}, total={global_vars.total_hosts}")
    # Formatierung der letzten Laufzeit
    last_run_formatted = None
    if global_vars.last_run_time:
        last_run_formatted = global_vars.last_run_time.strftime("%Y-%m-%d %H:%M:%S")
    start_time_str = None
    if global_vars.inventory_start_time:
        start_time_str = global_vars.inventory_start_time.strftime("%Y-%m-%d %H:%M:%S")
    with global_vars.processed_hosts_lock:
        return jsonify({
            'is_running': global_vars.is_running,
            'total_hosts': global_vars.total_hosts,
            'processed_hosts': global_vars.processed_hosts,
            'start_time': start_time_str,
            'last_run': last_run_formatted
        })

@app.route('/login', methods=['GET', 'POST'])
def login():
    '''if 'username' in session:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        if not username or not password:
            flash('Bitte füllen Sie beide Felder aus', 'error')
            return render_template('login.html')

        read_user_details()
        # Überprüfen der Anmeldedaten
        if username in username_list and user_auth(username, password):
            session['username'] = username
            session['login_time'] = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
            session['last_activity'] = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
            flash('Sie wurden erfolgreich angemeldet', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Ungültige Anmeldedaten', 'error')
            return render_template('login.html')
    return render_template('login.html')'''
    if 'username' in session:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        if not username or not password:
            flash('Bitte füllen Sie beide Felder aus', 'error')
            return render_template('login.html')

        # Direkte Nutzung von user_auth zur Authentifizierung
        if user_auth(username, password):
            session['username'] = username
            session['login_time'] = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
            session['last_activity'] = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
            flash('Sie wurden erfolgreich angemeldet', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Ungültige Anmeldedaten', 'error')
            return render_template('login.html')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash(f'Du wurdest erfolgreich abgemeldet')
    return redirect(url_for('login'))

@app.route('/inventory', methods=['GET'])
def get_inventory():
    """Zeigt die Software-Inventarliste an"""
    if 'username' not in session:
        return redirect(url_for('login'))
    log_request("INVENTORY_ACCESS")

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
    if 'username' not in session:
        return redirect(url_for('login'))

    if not global_vars.service_active.is_set():
        return jsonify({"status": "error", "message": "Service disabled"}), 403

    # Prüfe, ob bereits eine Inventur läuft
    if global_vars.is_running:
        return redirect('/inventory-progress')

    # Setze Variablen zurück
    global_vars.inventory_start_time = datetime.now()
    with global_vars.processed_hosts_lock:
        global_vars.processed_hosts = 0
    global_vars.is_running = True

    # Starte Inventurprozess im Hintergrund
    man_thread = threading.Thread(
        target=run_and_record,
        name="manual_inventory_thread",
        daemon=True)
    man_thread.start()

    return redirect('/inventory-progress')

@app.route('/stop-service', methods=['POST'])
@auth.login_required
def stop_service():
    if 'username' not in session:
        return jsonify({"status": "error", "message": "Authentication required"}), 401

    global_vars.service_active.clear()
    db_manager.set_metadata("service_active", 0)
    logging.warning("Service wurde deaktiviert")
    return jsonify({"status": "stopping"})

@app.route('/start-service', methods=['POST'])
@auth.login_required
def start_service():
    if 'username' not in session:
        return jsonify({"status": "error", "message": "Authentication required"}), 401
    global_vars.service_active.set()
    db_manager.conn.execute("UPDATE service_metadata SET service_active = 1 WHERE identifier = 1")
    db_manager.conn.commit()
    logging.info("Service wurde aktiviert")
    return jsonify({"status": "started"})

@app.route('/logs', methods=['GET'])
@auth.login_required
def show_logs():
    """Zeigt Logdateien an"""
    if 'username' not in session:
        return jsonify({"status": "error", "message": "Authentication required"}), 401
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
    if 'username' not in session:
        return jsonify({"status": "error", "message": "Authentication required"}), 401
    inventory_running = any(t.name == "manual_inventory_thread" for t in threading.enumerate())

    # Uptime berechnen
    uptime = datetime.now() - system_info['start_time']
    days = uptime.days
    hours, remainder = divmod(uptime.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    uptime_str = f"{days} Tag(e), {hours} Stunde(n), {minutes} Minute(n), {seconds} Sekunde(n)"
    connection = False
    if db_manager.conn is not None:
        connection = True

    last_run = get_last_run()

    last_run_value = db_manager.get_metadata("last_inventory_start")
    status_interval_weeks = int(db_manager.get_metadata("interval_weeks"))
    service_active_int = int(db_manager.get_metadata("service_active"))

    # ES BERECHNET NUR, WENN KEIN DATUM VORHANDEN IST! ICH WUNDER MICH DIE GANZE KACK ZEIT WARUM DAS NICHT GEHT
    next_run = db_manager.get_metadata("next_inventory_run")
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

@app.route('/account')
def account():
    """Kontoübersicht für den angemeldeten Benutzer"""

    if 'username' not in session:
        return redirect(url_for('login'))

    # Hier könnten man zusätzliche Benutzerinformationen aus einer Datenbank abrufen
    username = session['username']

    return render_template('account.html', username=username)

@app.route('/settings', methods=['GET', 'POST'])
@auth.login_required
def settings():
    """Einstellungsseite für Anpassungen"""
    if 'username' not in session:
        return jsonify({"status": "error", "message": "Authentication required"}), 401

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
    return render_template('500.html', e=e), 500
