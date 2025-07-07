import re
import logging
import os
import pyodbc
import configparser
from datetime import datetime

from cryptography.fernet import Fernet


def decrypt_password(encrypted_password: str, key_path: str = "config\\secret.key") -> str:
    with open(key_path, "rb") as key_file:
        key = key_file.read()
    fernet = Fernet(key)
    return fernet.decrypt(encrypted_password.encode()).decode()


class DatabaseManager:
    def __init__(self, config_file="config\\config.ini"):
        self.timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        log_file = f'logs\\{self.timestamp}-dbmanager.log'
        os.makedirs(os.path.dirname(log_file), exist_ok=True)

        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.INFO)
        if not self.logger.handlers:
            file_handler = logging.FileHandler(log_file)
            formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
            file_handler.setFormatter(formatter)
            self.logger.addHandler(file_handler)

        config = configparser.ConfigParser()
        config.read(config_file)

        encrypted_pwd_ps = config.get('db', 'password')
        self.pwd = decrypt_password(encrypted_pwd_ps)

        self.host = config.get('db', 'hostname')
        self.user = config.get('db', 'username')
        self.db = config.get('db', 'database')
        self.driver = config.get('db', 'driver')
        self.connection_str = (
            f"DRIVER={{{self.driver}}};"
            f"SERVER={self.host},1433;"
            f"DATABASE={self.db};"
            f"UID={self.user};"
            f"PWD={self.pwd};"
            f"TrustServerCertificate=yes;"
            f"Authentication=SqlPassword;"
        )
        self.conn = None
        self.table_name = "sw_list_dev_new"

    def connect_db(self):
        try:
            self.conn = pyodbc.connect(self.connection_str)
            self.logger.info("Verbindung zur Datenbank erfolgreich hergestellt.")
            print("[INFO] Verbindung erfolgreich.")
        except Exception as e:
            self.logger.error(f"Fehler beim Verbinden zur Datenbank: {e}")

    def db_disconnect(self):
        if self.conn:
            self.conn.close()
            self.logger.info(f"{self.timestamp} [INFO] - Verbindung zur Datenbank geschlossen.")
            print("[INFO] Verbindung zur Datenbank geschlossen.")

    def insert_software_to_test(self, software_list, hostname):
        table_name = "sw_list_dev_new"

        query = f"""
        INSERT INTO [{table_name}] (name, publisher, installDate, programSize, version, hostname, isNew)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """

        try:
            is_new = 1
            cursor = self.conn.cursor()
            for item in software_list:
                install_date_str = item.get('InstallDate')
                install_date = None
                if install_date_str:
                    try:
                        install_date = datetime.strptime(install_date_str, "%Y%m%d").date()
                    except Exception:
                        install_date = None
                publisher = item.get('Publisher')
                publisher_str = str(publisher)
                if publisher_str.startswith("Interflex"):
                    publisher_str = "Interflex Datensysteme GmbH & Co. KG"
                    cursor.execute(query, (
                        item.get('Name'),
                        publisher_str,
                        install_date,
                        item.get('Size'),
                        item.get('Version'),
                        hostname,
                        is_new
                    ))
                    self.conn.commit()
                else:
                    cursor.execute(query, (
                        item.get('Name'),
                        item.get('Publisher'),
                        install_date,
                        item.get('Size'),
                        item.get('Version'),
                        hostname,
                        is_new
                    ))
                    self.conn.commit()

            print("Softwareliste in Test-DB eingefügt.")
            self.logger.info({self.timestamp})

        except Exception as e:
            print(f"Fehler beim Einfügen in Test-DB: {e}")

    def reset_data_table(self):
        # Defining cursor variable for cleaner looking code
        cursor = self.conn.cursor()

        # Defined SQL-Query to update all old entries to keep track of the new and old data
        # TODO: Add Exception Handling, to stop the script.
        #  Before updating data add a backup (just in case to be safe)
        update_table = f"UPDATE {self.table_name} SET isNew = 0;"

        # Execute the code
        cursor.execute(update_table)
        cursor.commit()

        # If updated correctly continue
