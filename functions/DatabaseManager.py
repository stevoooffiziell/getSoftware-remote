# -*- coding: utf-8 -*-

import configparser
import logging
import os
import re
import threading
from datetime import datetime

import pyodbc
from cryptography.fernet import Fernet

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DEFAULT_CONFIG_FILE = os.path.join(PROJECT_ROOT, "config", "config.ini")
LOG_DIR = os.path.join(PROJECT_ROOT, "logs")

# Reentrant: Methoden, die den Lock halten, rufen sich teilweise gegenseitig auf
# (z.B. set_metadata -> connect_db). Die pyodbc-Verbindung wird von allen
# Threads geteilt, daher läuft jeder DB-Zugriff unter diesem Lock.
db_lock = threading.RLock()

# Spalten der Tabelle service_metadata. Spaltennamen lassen sich nicht als
# SQL-Parameter binden, deshalb werden sie gegen diese Liste geprüft.
METADATA_COLUMNS = frozenset({
    "service_active",
    "last_inventory_start",
    "next_inventory_run",
    "interval_weeks",
    "last_end_time",
    "identifier",
})

INSTALL_DATE_FORMATS = ("%Y%m%d", "%Y-%m-%d", "%d.%m.%Y")

_ARCH = r'x86_64|x64|x86|64-bit|32-bit'
# Architektur in Klammern, z.B. (x64), (64-bit), (x86_64)
_RE_ARCH_PAREN = re.compile(rf'\(\s*.*?({_ARCH}).*?\s*\)', re.IGNORECASE)
# Architektur-Begriffe außerhalb von Klammern
_RE_ARCH = re.compile(rf'\b({_ARCH})\b', re.IGNORECASE)
# Versionen, z.B. "14.40.33816", "v11.10"
_RE_VERSION = re.compile(r'\bv?\d+(\.\d+)*\b', re.IGNORECASE)
_RE_EMPTY_PAREN = re.compile(r'\(\s*\)')
# Leerzeichen um Bindestriche; Jahresbereiche wie 2015-2022 bleiben
_RE_DASH = re.compile(r'(?<=\D)\s*-\s*(?=\D)')
_RE_TRAILING = re.compile(r'[\s\-]+$')
_RE_SPACES = re.compile(r'\s{2,}')
_RE_IDENTIFIER = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]*$')


def clean_names(item):
    """Entfernt Architektur- und Versionsangaben aus einem Softwarenamen."""
    name = _RE_ARCH_PAREN.sub('', item)
    name = _RE_ARCH.sub('', name)
    name = _RE_VERSION.sub('', name)
    name = _RE_EMPTY_PAREN.sub('', name)
    name = _RE_DASH.sub('-', name)
    name = _RE_TRAILING.sub('', name)
    name = _RE_SPACES.sub(' ', name)
    return name.strip()


def parse_install_date(value):
    """Wandelt ein Installationsdatum in ein ``date`` um, ``None`` wenn unbekannt."""
    if not value:
        return None
    value = str(value).strip()
    for fmt in INSTALL_DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def normalize_publisher(publisher):
    """Vereinheitlicht unterschiedliche Schreibweisen desselben Herstellers."""
    publisher = str(publisher or '')
    if "Interflex" in publisher:
        return "Interflex Datensysteme GmbH & Co. KG"
    if "Microsoft" in publisher:
        return "Microsoft Corporation"
    return publisher


class DatabaseManager:
    _instance = None
    _initialized = False
    _instance_lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        """Singleton-Pattern: Ensures that the instance exists only once"""
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, config_file=DEFAULT_CONFIG_FILE):
        """
        Initializes database connection only once

        :param config_file: path to the ``config.ini``
        """
        if self._initialized:
            return

        # Präfixe für Konsolenausgaben
        self.info = "[INFO]    |"
        self.debug = "[DEBUG]   |"
        self.warning = "[WARNING] |"
        self.error = "[ERROR]   |"

        self.config_file = config_file
        self.existing_config = os.path.exists(config_file)
        self.conn = None

        config = configparser.ConfigParser()
        if not config.read(self.config_file):
            raise FileNotFoundError(f"Config file not found: {self.config_file}")
        if not config.has_section('db'):
            raise Exception("Config file does not have [db] section")

        self.pwd = config.get('db', 'pass')
        self.host = config.get('db', 'host', fallback='10.100.13.55')
        self.user = config.get('db', 'user', fallback='db-admin')
        self.db = config.get('db', 'database')
        self.driver = config.get('db', 'driver')
        self.backup_table = config.get('db', 'backup-table')
        self.table_name = config.get('db', 'prod-table')

        # Tabellennamen landen direkt im SQL-Text -> einmalig validieren
        for table in (self.table_name, self.backup_table):
            if not _RE_IDENTIFIER.match(table):
                raise ValueError(f"Invalid table name: {table}")

        self.__passw = decrypt_password(self.pwd)
        self.connection_str = (
            f"DRIVER={{{self.driver}}};"
            f"SERVER={self.host},1433;"
            f"DATABASE={self.db};"
            f"UID={self.user};"
            f"PWD={self.__passw};"
            "TrustServerCertificate=yes;"
            "Authentication=SqlPassword;"
        )

        # Zeitstempel für Logs
        self.time_dmy = self.get_timestamp("dmy")
        self.time_hms = self.get_timestamp("hms")

        print(f"{self.get_timestamp('')} | {self.info} Initializing logger...")
        self._init_logger()

        self._initialize_db_connection()
        self._ensure_metadata_table()
        self.ensure_tables_exist()
        self._initialized = True
        self.logger.info("DatabaseManager initialized")
        print(f"{self.get_logprint_info()} Database connection established.")

    def _init_logger(self):
        os.makedirs(LOG_DIR, exist_ok=True)
        self.log_file = os.path.join(LOG_DIR, f'{self.time_dmy}_{self.time_hms}-dbmanager.log')

        self.logger = logging.getLogger('DatabaseManager')
        self.logger.setLevel(logging.INFO)

        # Add only one Handler if none exists
        if not self.logger.handlers:
            file_handler = logging.FileHandler(self.log_file, encoding='utf-8')
            file_handler.setFormatter(
                logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
            self.logger.addHandler(file_handler)

    @staticmethod
    def get_timestamp(format_var):
        now = datetime.now()
        if format_var == "dmy":
            return now.strftime("%d-%m-%Y")
        elif format_var == "hms":
            return now.strftime("%H-%M-%S")
        return now.strftime("%d-%m-%Y %H-%M-%S")

    def get_logprint_info(self):
        return f"{self.get_timestamp('')} | {self.info}"

    def get_logprint_error(self):
        return f"{self.get_timestamp('')} | {self.error}"

    def get_logprint_debug(self):
        return f"{self.get_timestamp('')} | {self.debug}"

    def get_logprint_warning(self):
        return f"{self.get_timestamp('')} | {self.warning}"

    def _initialize_db_connection(self):
        """Opens the database connection described by the ``config_file``."""
        try:
            if not self.driver:
                raise ValueError("Database driver not configured")

            self.conn = pyodbc.connect(self.connection_str)
            self.conn.autocommit = False

            self.logger.info("Database connection established successfully")
            print(f"{self.get_logprint_info()} Connected to database {self.db}")
        except Exception as e:
            self.logger.error(f"Connection failed: {str(e)}")
            print(f"{self.get_logprint_error()} Database connection failed: {str(e)}")
            self.conn = None
            raise

    def _ensure_metadata_table(self):
        """Ensures that the metadata table exists in the database"""
        create_table_sql = """
        IF NOT EXISTS (
            SELECT * FROM INFORMATION_SCHEMA.TABLES
            WHERE TABLE_NAME = 'service_metadata'
        )
        BEGIN
            CREATE TABLE service_metadata (
                service_active INT,
                last_inventory_start DATETIME,
                next_inventory_run DATETIME,
                interval_weeks INT,
                last_end_time DATETIME,
                identifier INT
            );

            INSERT INTO service_metadata (
                service_active,
                last_inventory_start,
                next_inventory_run,
                interval_weeks,
                last_end_time,
                identifier
            ) VALUES (
                0,
                NULL,
                DATEADD(WEEK, 2, GETDATE()),
                2,
                NULL,
                1
            );
        END
        """
        try:
            with db_lock:
                self.connect_db()
                self.conn.execute(create_table_sql)
                self.conn.commit()
            self.logger.info("Service metadata table verified")
        except Exception as e:
            self.logger.error(f"Error creating metadata table: {str(e)}")
            raise

    def connect_db(self):
        """
        Stellt sicher, dass eine DB-Verbindung besteht

        :return: die offene ``pyodbc``-Verbindung
        """
        with db_lock:
            if self.conn is None:
                self._initialize_db_connection()
            return self.conn

    def _reset_connection(self):
        """Verwirft die Verbindung, damit der nächste Zugriff neu verbindet."""
        with db_lock:
            if self.conn is not None:
                try:
                    self.conn.close()
                except Exception:
                    pass
                self.conn = None

    def fetch_all(self, sql, *params):
        """
        Führt eine lesende Abfrage threadsicher aus.

        :return: ``(columns, rows)``
        """
        with db_lock:
            try:
                cursor = self.connect_db().cursor()
                try:
                    cursor.execute(sql, *params)
                    columns = [column[0] for column in cursor.description]
                    return columns, cursor.fetchall()
                finally:
                    cursor.close()
            except pyodbc.OperationalError:
                # Verbindung abgerissen -> beim nächsten Aufruf neu aufbauen
                self._reset_connection()
                raise

    def dependencies_check(self):
        """Checks if a configuration file is existing"""
        if self.existing_config:
            self.logger.info("Configuration file verified")
            print(f"{self.get_logprint_info()} Configuration file is set.")
        else:
            self.logger.error("Config file missing")
            print(f"{self.get_logprint_error()} Config file is not in the expected directory!")
            raise FileNotFoundError("Configuration file missing")

    def close(self):
        try:
            with db_lock:
                if self.conn is not None:
                    self.conn.close()
                    self.conn = None
            self.logger.info(f"Connection to database {self.db} has been closed successfully.")
            print(f"{self.get_logprint_info()} Connection to database {self.db} has been closed successfully")
        except Exception as e:
            self.logger.error(f"The connection to the database {self.db} hasn't been closed successfully!")
            self.logger.error(f"Error description: {e}")
            print(
                f"{self.get_logprint_error()} The connection to the database {self.db} hasn't been closed successfully!")
            print(f"{self.get_logprint_error()} An unknown error has occured: {e}")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """context manager: disconnect automatically"""
        self.close()

    def ensure_tables_exist(self):
        """ensures that required tables exist"""
        # TODO: backup table - implement it or create a backup SQL-file instead?
        try:
            with db_lock:
                self.connect_db()
                self.conn.execute(queries(self.table_name))
                self.conn.commit()
            self.logger.info(f"Checked/Created table {self.table_name}")
        except Exception as e:
            self.logger.error(f"Table creation failed: {str(e)}")
            raise

    @staticmethod
    def _check_metadata_key(key):
        if key not in METADATA_COLUMNS:
            raise ValueError(f"Unknown metadata key: {key}")

    def get_metadata(self, key):
        """
        Holt einen Metadaten-Wert aus der Datenbank

        :param key: Spaltenname in ``service_metadata``
        :return: der Wert oder ``None``
        """
        try:
            self._check_metadata_key(key)
            _, rows = self.fetch_all(f"SELECT TOP 1 {key} FROM service_metadata")
            return rows[0][0] if rows else None
        except Exception as e:
            self.logger.error(f"Error getting metadata for key '{key}': {str(e)}")
            return None

    def set_metadata(self, key, value):
        """Setzt einen Metadaten-Wert in der Datenbank"""
        try:
            self._check_metadata_key(key)
            with db_lock:
                conn = self.connect_db()
                try:
                    cursor = conn.execute(
                        f"UPDATE service_metadata SET {key} = ? WHERE identifier = 1", value)
                    if cursor.rowcount == 0:
                        # Fallback: Zeile existiert noch nicht
                        conn.execute(
                            f"INSERT INTO service_metadata ({key}, identifier) VALUES (?, 1)", value)
                    conn.commit()
                except Exception:
                    conn.rollback()
                    raise
            self.logger.info(f"Metadata updated: {key} = {value}")
            return True
        except Exception as e:
            self.logger.error(f"Error setting metadata for key '{key}': {str(e)}")
            print(f"{self.get_logprint_error()} Error setting metadata: {str(e)}")
            return False

    def set_starttime(self, value=None):
        return self.set_metadata("last_inventory_start", value or datetime.now())

    def set_nexttime(self, value):
        return self.set_metadata("next_inventory_run", value)

    def insert_software(self, software_list, hostname):
        """
        Insert the values from the gathered software list into the database

        :param software_list: list of dicts (Name, Publisher, InstallDate, Size, Version)
        :param hostname:
        """
        query = f"""
                INSERT INTO [{self.table_name}] (name, publisher, installDate, programSize, version, hostname, isNew)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """
        # Die Aufbereitung braucht keine DB und läuft daher außerhalb des Locks
        rows = [
            (
                clean_names(str(item.get('Name') or 'Unknown'))[:90],
                normalize_publisher(item.get('Publisher'))[:90],
                parse_install_date(item.get('InstallDate')),
                item.get('Size') or 0,
                str(item.get('Version') or '0.0.0')[:50],
                hostname[:80],
                True,  # isNew
            )
            for item in software_list
        ]
        if not rows:
            self.logger.info(f"No records to insert for {hostname}")
            return

        try:
            with db_lock:  # Thread-security
                cursor = self.connect_db().cursor()
                try:
                    # Ein Roundtrip für alle Zeilen statt eines pro Zeile
                    cursor.fast_executemany = True
                    cursor.executemany(query, rows)
                finally:
                    cursor.close()
                self.conn.commit()

            self.logger.info(f"Inserted {len(rows)} records for {hostname}")
            print(f"{self.get_logprint_info()} Inserted {len(rows)} items for {hostname}")
        except Exception as e:
            self.logger.error(f"Insert failed for {hostname}: {str(e)}")
            with db_lock:
                if self.conn:
                    self.conn.rollback()
            raise


def queries(table):
    """
    Generates sql-query. Creates a new table if the given name is not existing

    :param table:
    :return: ``str``
    """
    # Ensure that the table name is valid
    if not _RE_IDENTIFIER.match(table):
        raise ValueError(f"Invalid table name: {table}")

    return f"""
    IF NOT EXISTS (
        SELECT * FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_NAME = '{table}' AND TABLE_SCHEMA = 'dbo'
    )
    BEGIN
        CREATE TABLE dbo.{table} (
            name VARCHAR(90),
            publisher VARCHAR(90),
            installDate DATE,
            programSize INT,
            version NVARCHAR(50),
            hostname VARCHAR(80),
            isNew BIT NOT NULL
        );
    END
    """


def decrypt_password(encrypted_password: str, key_path: str = None) -> str:
    """
    Uses the ``secret.key`` to decrypt the previously encrypted password.

    :param encrypted_password:
    :param key_path: path of the secret.key, defaults to ``config/secret.key``
    :return: str
    """
    if not key_path:
        key_path = os.path.join(PROJECT_ROOT, "config", "secret.key")
    try:
        with open(key_path, "rb") as key_file:
            key = key_file.read()
        return Fernet(key).decrypt(encrypted_password.encode()).decode()
    except Exception as e:
        logging.error(f"Decryption failed: {str(e)}")
        raise RuntimeError("Password decryption error")
