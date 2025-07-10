# -*- coding: utf-8 -*-

from flask import Flask, render_template, request, jsonify, redirect, url_for
from scheduler_service import scheduler, run_inventory
from datetime import datetime
import threading

app = Flask(__name__)

# In-Memory-Log-Speicher
execution_logs = {"current": "", "history": []}

# Starte den Scheduler beim App-Start
if not scheduler.running:
    scheduler.start()


@app.route('/')
def dashboard():
    return render_template('dashboard.html')


@app.route('/run-inventory', methods=['POST'])
def trigger_inventory():
    # Führe den Job sofort in einem separaten Thread aus
    def run_inventory_thread():
        execution_logs["current"] = f"{datetime.now()} - Starting manual inventory...\n"
        try:
            run_inventory()
            execution_logs["current"] += f"{datetime.now()} - Inventory completed successfully\n"
            execution_logs["history"].append({
                "timestamp": datetime.now().strftime("%Y-%m-%d %H-%M-%S"),
                "log": execution_logs["current"],
                "status": "success"
            })
        except Exception as e:
            execution_logs["current"] += f"{datetime.now().strftime("%Y-%m-%d %H-%M-%S")} - Error: {str(e)}\n"
            execution_logs["history"].append({
                "timestamp": datetime.now().strftime("%Y-%m-%d %H-%M-%S"),
                "log": execution_logs["current"],
                "status": "error"
            })

    thread = threading.Thread(target=run_inventory_thread)
    thread.start()

    return jsonify({"status": "started"})


@app.route('/logs')
def get_logs():
    return jsonify({
        "current": execution_logs["current"],
        "history": execution_logs["history"][-10:]  # Letzte 10 Einträge
    })


@app.route('/settings', methods=['GET', 'POST'])
def settings():
    if request.method == 'POST':
        new_interval = int(request.form.get('interval', 2))
        try:
            scheduler.reschedule_job(
                'periodic_inventory',
                trigger='interval',
                weeks=new_interval
            )
            return redirect(url_for('settings'))
        except Exception as e:
            return f"Error updating interval: {str(e)}", 400

    try:
        job = scheduler.get_job('periodic_inventory')
        current_interval = job.trigger.interval.weeks if job else 2
        return render_template('settings.html', interval=current_interval)
    except Exception as e:
        return f"Error retrieving settings: {str(e)}", 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
