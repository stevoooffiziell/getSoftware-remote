# -*- coding: utf-8 -*-

import logging
import os
import platform
import secrets
import socket
import threading
from datetime import datetime, timedelta

import flask
from dotenv import load_dotenv
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, session
from flask_httpauth import HTTPBasicAuth

import vars.global_vars as global_vars
from app.scheduler_service import INVENTORY_THREAD_NAME, db_manager, start_inventory_thread
from secret.user_management import user_auth
from vars.paths import LOG_DIR

load_dotenv()

app = Flask(__name__, template_folder='templates', static_folder="static")
app.secret_key = os.getenv('SECRET_KEY') or secrets.token_hex(32)
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=1)

auth = HTTPBasicAuth()

PORT = 5000
DATE_FMT = "%d.%m.%Y %H:%M:%S"

logging.basicConfig(filename=os.path.join(LOG_DIR, f'{db_manager.get_timestamp("dmy")}-app.log'),
                    level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')

system_info = {
    'hostname': socket.gethostname(),
    'ip_address': socket.gethostbyname(socket.gethostname()),
    'os': platform.platform(),
    'python_version': platform.python_version(),
    'flask_version': flask.__version__,
    'start_time': datetime.now(),
}


def sync_service_status():
    """Übernimmt den Service-Status aus der Datenbank, gibt den DB-Wert zurück."""
    value = db_manager.get_metadata("service_active")
    if value == 1:
        global_vars.service_active.set()
    else:
        global_vars.service_active.clear()
    return value


try:
    _active = sync_service_status()
    print(f"Service status synchronized from database: {'Active' if _active == 1 else 'Inactive'}")
except Exception as e:
    print(f"Error synchronizing service status: {e}")

print("\n" + "=" * 80)
print("Software Inventory Service gestartet")
print(f"Startzeit: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print(f"Website ist zugänglich über {system_info['ip_address']}:{PORT}")
print("=" * 80 + "\n")


def format_dt(value, fmt=DATE_FMT, default="Noch nicht ausgeführt"):
    return value.strftime(fmt) if isinstance(value, datetime) else default


def log_request(action):
    """Loggt Zugriffe in einer Datei pro Tag."""
    log_file = os.path.join(LOG_DIR, f"{datetime.now():%Y-%m-%d}.log")
    try:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now()}] {action} {request.remote_addr} {request.url}\n")
    except OSError as e:
        logging.error(f"Log-Schreibfehler: {e}")


@auth.verify_password
def verify_password(username, password):
    return username if user_auth(username, password) else None


@app.before_request
def require_login():
    """Alle Routen außer Login und statischen Dateien erfordern eine Sitzung."""
    if request.endpoint in ('login', 'static'):
        return None
    if 'username' not in session:
        if request.path.startswith(('/start-service', '/stop-service', '/reset-database')):
            return jsonify({"status": "error", "message": "Authentication required"}), 401
        return redirect(url_for('login'))
    session['last_activity'] = datetime.now().strftime(DATE_FMT)
    return None


@app.route('/')
@app.route('/dashboard')
def dashboard():
    row = db_manager.fetch_one(
        f"SELECT COUNT(DISTINCT hostname), COUNT(DISTINCT name), COUNT(name), COUNT(DISTINCT publisher) "
        f"FROM dbo.{db_manager.table_name}")
    count_hosts, count_sw, count_sw_all, count_publisher = row if row else (0, 0, 0, 0)

    return render_template('dashboard.html',
                           count_hosts=count_hosts,
                           count_sw_all=count_sw_all,
                           count_sw=count_sw,
                           count_publisher=count_publisher,
                           last_run=format_dt(db_manager.get_metadata("last_inventory_start")),
                           next_run=format_dt(db_manager.get_metadata("next_inventory_run"),
                                              "%Y-%m-%d %H:%M:%S", "-"))


@app.route('/inventory-progress')
def inventory_progress():
    with global_vars.processed_hosts_lock:
        processed = global_vars.processed_hosts
        total = global_vars.total_hosts
    percentage = round(processed / total * 100) if total else 0
    return render_template('process.html',
                           percentage=percentage,
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
            'start_time': format_dt(global_vars.inventory_start_time, "%Y-%m-%dT%H:%M:%S", None),
            'last_run': format_dt(global_vars.last_run_time, "%Y-%m-%d %H:%M:%S", None),
        })


@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'username' in session:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        if not username or not password:
            flash('Bitte füllen Sie beide Felder aus', 'error')
        elif user_auth(username, password):
            now = datetime.now().strftime(DATE_FMT)
            session['username'] = username
            session['login_time'] = now
            session['last_activity'] = now
            flash('Sie wurden erfolgreich angemeldet', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Ungültige Anmeldedaten', 'error')
    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    flash('Du wurdest erfolgreich abgemeldet')
    return redirect(url_for('login'))


@app.route('/inventory')
def get_inventory():
    """Zeigt die Software-Inventarliste an."""
    log_request("INVENTORY_ACCESS")
    cursor = db_manager.connect_db().cursor()
    cursor.execute(f"SELECT * FROM dbo.{db_manager.table_name}")
    columns = [column[0] for column in cursor.description]
    inventory = [dict(zip(columns, row)) for row in cursor.fetchall()]
    return render_template('inventory.html', inventory=inventory)


@app.route('/run-inventory', methods=['GET', 'POST'])
@auth.login_required
def run_inventory():
    if not global_vars.service_active.is_set():
        return render_template("403.html"), 403
    start_inventory_thread()
    return redirect(url_for('inventory_progress'))


def _set_service_active(active: bool):
    if not db_manager.set_metadata("service_active", int(active)):
        return jsonify({"status": "error", "message": "Datenbank-Update fehlgeschlagen"}), 500
    if active:
        global_vars.service_active.set()
        logging.info("Service wurde aktiviert")
        return jsonify({"status": "started"})
    global_vars.service_active.clear()
    logging.warning("Service wurde deaktiviert")
    return jsonify({"status": "stopping"})


@app.route('/stop-service', methods=['POST'])
@auth.login_required
def stop_service():
    return _set_service_active(False)


@app.route('/start-service', methods=['POST'])
@auth.login_required
def start_service():
    return _set_service_active(True)


@app.route('/reset-database', methods=['POST'])
@auth.login_required
def reset_database():
    """Löscht alle Inventardaten (Bestätigung erfolgt im Frontend)."""
    if global_vars.is_running:
        return jsonify({"status": "error", "message": "Es läuft gerade eine Inventur"}), 409
    try:
        db_manager.delete_inventory()
        log_request("DATABASE_RESET")
        return jsonify({"status": "success"})
    except Exception as e:
        logging.error(f"Database reset failed: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/logs')
@auth.login_required
def show_logs():
    """Zeigt Logdateien an."""
    log_request("LOGS_ACCESS")
    log_files = sorted(f for f in os.listdir(LOG_DIR) if f.endswith('.log') and not f.startswith('app'))

    requested_log = request.args.get('file')
    if not requested_log:
        return render_template('logs.html', logs=log_files)

    # Nur Dateien aus der Liste zulassen (verhindert Path Traversal)
    if requested_log not in log_files:
        return render_template('error.html', error="Log-Datei nicht gefunden"), 404
    try:
        with open(os.path.join(LOG_DIR, requested_log), 'r', encoding="utf-8", errors="replace") as f:
            content = f.read()
        return render_template('log_viewer.html', log_content=content, log_file=requested_log)
    except OSError as e:
        logging.error(f"Log-Lesefehler: {e}")
        return render_template('error.html', error="Fehler beim Lesen der Log-Datei"), 500


@app.route('/status')
def service_status():
    """Statusseite mit Service-, Inventur- und Systeminformationen."""
    uptime = datetime.now() - system_info['start_time']
    hours, remainder = divmod(uptime.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    threads = sum(1 for t in threading.enumerate() if t.name == INVENTORY_THREAD_NAME)

    return render_template("status.html",
                           inventory_running=threads > 0,
                           service_active=sync_service_status(),
                           system_info=system_info,
                           uptime=f"{uptime.days} Tag(e), {hours} Stunde(n), "
                                  f"{minutes} Minute(n), {seconds} Sekunde(n)",
                           last_restart=system_info['start_time'].strftime("%Y-%m-%d %H:%M:%S"),
                           last_run=format_dt(db_manager.get_metadata("last_inventory_start")),
                           interval_weeks=db_manager.get_metadata("interval_weeks"),
                           threads=threads,
                           connection=db_manager.is_connected(),
                           next_run=format_dt(db_manager.get_metadata("next_inventory_run"), default="-"))


@app.route('/account')
def account():
    return render_template('account.html', username=session['username'])


@app.route('/settings', methods=['GET', 'POST'])
@auth.login_required
def settings():
    interval_weeks = db_manager.get_metadata("interval_weeks")

    if request.method == 'POST':
        try:
            new_interval = int(request.form.get('interval', interval_weeks))
            if new_interval < 1:
                raise ValueError("Intervall muss mindestens 1 Woche betragen")
            if not db_manager.set_metadata("interval_weeks", new_interval):
                raise RuntimeError("Datenbank-Update fehlgeschlagen")
            return render_template('settings.html', interval=new_interval,
                                   message=f"Intervall auf {new_interval} Wochen gesetzt")
        except (ValueError, RuntimeError) as e:
            return render_template('settings.html', interval=interval_weeks,
                                   error=f"Ungültiges Intervall: {e}")

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
