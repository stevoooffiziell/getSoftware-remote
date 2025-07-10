import pyodbc
from flask import current_app


def get_software_stats():
    config = current_app.config['DB_CONFIG']
    conn = pyodbc.connect(config['connection_string'])
    cursor = conn.cursor()

    # Top 10 Software
    cursor.execute(
        f"SELECT TOP 10 name, COUNT(*) as count FROM {config['table_name']} GROUP BY name ORDER BY count DESC")
    top_software = cursor.fetchall()

    # Software pro Host
    cursor.execute(f"SELECT hostname, COUNT(*) as count FROM {config['table_name']} GROUP BY hostname")
    host_distribution = cursor.fetchall()

    # Publisher-Verteilung
    cursor.execute(f"SELECT publisher, COUNT(*) as count FROM {config['table_name']} GROUP BY publisher")
    publisher_stats = cursor.fetchall()

    return {
        "top_software": [{"name": row[0], "count": row[1]} for row in top_software],
        "host_distribution": [{"host": row[0], "count": row[1]} for row in host_distribution],
        "publisher_stats": [{"publisher": row[0], "count": row[1]} for row in publisher_stats]
    }