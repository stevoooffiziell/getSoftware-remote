# -*- coding: utf-8 -*-

import configparser
import logging
import os
import re
import threading
import time
from datetime import datetime

import pyodbc
from cryptography.fernet import Fernet

from vars.paths import CONFIG_FILE, LOG_DIR, SECRET_KEY_FILE

db_lock = threading.RLock()

CONNECT_TIMEOUT_SEC = 5     # Abbruch eines einzelnen Verbindungsversuchs
RETRY_COOLDOWN_SEC = 30     # Wartezeit nach einem Fehlschlag bis zum nächsten Versuch


class DatabaseUnavailableError(ConnectionError):
    """Die Datenbank ist (derzeit) nicht erreichbar."""

# Spalten der Tabelle service_metadata, die gelesen/geschrieben werden dürfen
METADATA_KEYS = {
    "service_active",
    "last_inventory_start",
    "next_inventory_run",
    "interval_weeks",
    "last_end_time",
}

_ARCH = r'(x64|x86|64-bit|32-bit|x86_64)'
_RE_ARCH_PARENS = re.compile(r'\(\s*.*?' + _ARCH + r'.*?\s*\)', re.IGNORECASE)
_RE_ARCH = re.compile(r'\b' + _ARCH + r'\b', re.IGNORECASE)
_RE_VERSION = re.compile(r'\bv?\d+(\.\d+)*\b', re.IGNORECASE)
_RE_EMPTY_PARENS = re.compile(r'\(\s*\)')
_RE_DASH = re.compile(r'(?<=\D)\s*-\s*(?=\D)')
_RE_TRAILING = re.compile(r'[\s\-]+$')
_RE_SPACES = re.compile(r'\s{2,}')


def clean_names(item: str) -> str:
    """Entfernt Architektur- und Versionsangaben aus einem Softwarenamen."""
    name = _RE_ARCH_PARENS.sub('', item)
    name = _RE_ARCH.sub('', name)
    name = _RE_VERSION.sub('', name)
    name = _RE_EMPTY_PARENS.sub('', name)
    name = _RE_DASH.sub('-', name)
    name = _RE_TRAILING.sub('', name)
    name = _RE_SPACES.sub(' ', name)
    return name.strip()


def normalize_publisher(publisher: str) -> str:
    """Vereinheitlicht unterschiedliche Schreibweisen desselben Herstellers."""
    if "Interflex" in publisher:
        return "Interflex Datensysteme GmbH & Co. KG"
    if "Microsoft" in publisher:
        return "Microsoft Corporation"
    return publisher


def parse_install_date(value):
    """Parst ein Installationsdatum in verschiedenen Formaten, sonst None."""
    if not value:
        return None
    for fmt in ("%Y%m%d", "%Y-%m-%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(str(value), fmt).date()
        except ValueError:
            continue
    return None


def decrypt_password(encrypted_password: str, key_path: str = SECRET_KEY_FILE) -> str:
    """Entschlüsselt ein mit ``secret.key`` (Fernet) verschlüsseltes Passwort."""
    try:
        with open(key_path, "rb") as key_file:
            fernet = Fernet(key_file.read())
        return fernet.decrypt(encrypted_password.encode()).decode()
    except Exception as e:
        logging.error(f"Decryption failed: {e}")
        raise RuntimeError("Password decryption error") from e


def create_table_query(table: str) -> str:
    """Erzeugt das SQL, das die Inventartabelle anlegt, falls sie nicht existiert."""
    if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', table):
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


METADATA_TABLE_QUERY = """
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
        service_active, last_inventory_start, next_inventory_run,
        interval_weeks, last_end_time, identifier
    ) VALUES (0, NULL, DATEADD(WEEK, 2, GETDATE()), 2, NULL, 1);
END
"""


class DatabaseManager:
    """Singleton für die Verbindung zur SQL-Server-Datenbank."""
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, config_file: str = CONFIG_FILE):
        if self._initialized:
            return

        config = configparser.ConfigParser()
        if not config.read(config_file):
            raise FileNotFoundError(f"Config file not found: {config_file}")
        if not config.has_section('db'):
            raise ValueError("Config file does not have [db] section")

        self.config_file = config_file
        self.host = config.get('db', 'host')
        self.user = config.get('db', 'user')
        self.db = config.get('db', 'database')
        self.driver = config.get('db', 'driver')
        self.table_name = config.get('db', 'prod-table')
        if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', self.table_name):
            raise ValueError(f"Invalid table name: {self.table_name}")

        self.connection_str = (
            f"DRIVER={{{self.driver}}};"
            f"SERVER={self.host},1433;"
            f"DATABASE={self.db};"
            f"UID={self.user};"
            f"PWD={decrypt_password(config.get('db', 'pass'))};"
            "TrustServerCertificate=yes;"
            "Authentication=SqlPassword;"
        )

        self.info = "[INFO]    |"
        self.debug = "[DEBUG]   |"
        self.warning = "[WARNING] |"
        self.error = "[ERROR]   |"

        self._init_logger()
        self.conn = None
        self._tables_ready = False
        self._last_failure = 0.0
        self._initialized = True
        self.logger.info("DatabaseManager initialized")

        # Erster Verbindungsversuch; schlägt er fehl, startet die App trotzdem
        # und verbindet sich beim nächsten Zugriff erneut.
        if self.is_connected():
            print(f"{self.get_logprint_info()} Database connection established.")
        else:
            print(f"{self.get_logprint_warning()} Database not reachable - starting without database, "
                  f"retrying on next access.")

    # ------------------------------------------------------------------ Logging
    def _init_logger(self):
        self.logger = logging.getLogger('DatabaseManager')
        self.logger.setLevel(logging.INFO)
        if not self.logger.handlers:
            log_file = os.path.join(
                LOG_DIR, f"{self.get_timestamp('dmy')}_{self.get_timestamp('hms')}-dbmanager.log")
            handler = logging.FileHandler(log_file, encoding="utf-8")
            handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
            self.logger.addHandler(handler)

    @staticmethod
    def get_timestamp(format_var: str = "") -> str:
        now = datetime.now()
        if format_var == "dmy":
            return now.strftime("%d-%m-%Y")
        if format_var == "hms":
            return now.strftime("%H-%M-%S")
        return now.strftime("%d-%m-%Y %H-%M-%S")

    def get_logprint_info(self):
        return f"{self.get_timestamp()} | {self.info}"

    def get_logprint_error(self):
        return f"{self.get_timestamp()} | {self.error}"

    def get_logprint_debug(self):
        return f"{self.get_timestamp()} | {self.debug}"

    def get_logprint_warning(self):
        return f"{self.get_timestamp()} | {self.warning}"

    # --------------------------------------------------------------- Verbindung
    def connect_db(self):
        """Gibt eine gültige DB-Verbindung zurück und baut sie bei Bedarf neu auf.

        :raises DatabaseUnavailableError: wenn die Datenbank nicht erreichbar ist
        """
        with db_lock:
            if self.conn is not None:
                try:
                    self.conn.execute("SELECT 1")
                    return self.conn
                except pyodbc.Error:
                    self.logger.warning("Existing connection invalid, reconnecting...")
                    self.conn = None

            # Nach einem Fehlschlag nicht bei jedem Zugriff erneut warten
            wait = RETRY_COOLDOWN_SEC - (time.monotonic() - self._last_failure)
            if self._last_failure and wait > 0:
                raise DatabaseUnavailableError(f"Datenbank nicht erreichbar (nächster Versuch in {wait:.0f} s)")

            try:
                conn = pyodbc.connect(self.connection_str, autocommit=False, timeout=CONNECT_TIMEOUT_SEC)
                if not self._tables_ready:
                    conn.execute(METADATA_TABLE_QUERY)
                    conn.execute(create_table_query(self.table_name))
                    conn.commit()
                    self._tables_ready = True
                    self.logger.info(f"Checked/created tables service_metadata and {self.table_name}")
            except pyodbc.Error as e:
                self._last_failure = time.monotonic()
                self.logger.error(f"Connection failed: {e}")
                print(f"{self.get_logprint_error()} Database connection failed: {e}")
                raise DatabaseUnavailableError("Datenbank nicht erreichbar") from e

            self.conn = conn
            self._last_failure = 0.0
            self.logger.info("Database connection established successfully")
            print(f"{self.get_logprint_info()} Connected to database {self.db}")
            return self.conn

    def is_connected(self) -> bool:
        try:
            self.connect_db()
            return True
        except DatabaseUnavailableError:
            return False

    def close(self):
        if self.conn is not None:
            self.conn.close()
            self.conn = None
            self.logger.info(f"Connection to database {self.db} closed.")

    def fetch_one(self, query: str, *params):
        with db_lock:
            cursor = self.connect_db().cursor()
            cursor.execute(query, *params)
            return cursor.fetchone()

    # ---------------------------------------------------------------- Metadaten
    def get_metadata(self, key: str):
        """Liest einen Metadaten-Wert, ``None`` bei Fehler."""
        if key not in METADATA_KEYS:
            raise ValueError(f"Unknown metadata key: {key}")
        try:
            row = self.fetch_one(f"SELECT TOP 1 {key} FROM service_metadata")
            return row[0] if row else None
        except Exception as e:
            self.logger.error(f"Error getting metadata for key '{key}': {e}")
            return None

    def set_metadata(self, key: str, value) -> bool:
        """Schreibt einen Metadaten-Wert, legt die Zeile bei Bedarf an."""
        if key not in METADATA_KEYS:
            raise ValueError(f"Unknown metadata key: {key}")
        try:
            with db_lock:
                conn = self.connect_db()
                cursor = conn.cursor()
                cursor.execute(f"UPDATE service_metadata SET {key} = ? WHERE identifier = 1", value)
                if cursor.rowcount == 0:
                    cursor.execute(f"INSERT INTO service_metadata ({key}, identifier) VALUES (?, 1)", value)
                conn.commit()
            self.logger.info(f"Metadata updated: {key} = {value}")
            return True
        except Exception as e:
            self.logger.error(f"Error setting metadata for key '{key}': {e}")
            print(f"{self.get_logprint_error()} Error setting metadata '{key}': {e}")
            return False

    # ---------------------------------------------------------------- Inventar
    def insert_software(self, software_list, hostname):
        """Ersetzt die Software-Liste eines Hosts in der Datenbank.

        Alte Einträge des Hosts werden in derselben Transaktion gelöscht, sodass bei
        einem Fehler die bisherigen Daten erhalten bleiben.
        """
        query = (f"INSERT INTO [{self.table_name}] "
                 f"(name, publisher, installDate, programSize, version, hostname, isNew) "
                 f"VALUES (?, ?, ?, ?, ?, ?, ?)")

        rows = []
        for item in software_list:
            try:
                size = int(item.get('Size') or 0)
            except (TypeError, ValueError):
                size = 0
            rows.append((
                clean_names(str(item.get('Name') or 'Unknown'))[:90],
                normalize_publisher(str(item.get('Publisher') or ''))[:90],
                parse_install_date(item.get('InstallDate')),
                size,
                str(item.get('Version') or '0.0.0')[:50],
                hostname,
                True,
            ))

        if not rows:
            return

        try:
            with db_lock:
                conn = self.connect_db()
                cursor = conn.cursor()
                cursor.execute(f"DELETE FROM [{self.table_name}] WHERE hostname = ?", hostname)
                deleted = cursor.rowcount
                cursor.fast_executemany = True
                cursor.executemany(query, rows)
                conn.commit()
            self.logger.info(f"Replaced {deleted} with {len(rows)} records for {hostname}")
            print(f"{self.get_logprint_info()} Replaced {deleted} with {len(rows)} items for {hostname}")
        except Exception as e:
            self.logger.error(f"Insert failed for {hostname}: {e}")
            if self.conn:
                self.conn.rollback()
            raise

    def delete_hosts_not_in(self, hostnames) -> int:
        """Löscht die Einträge aller Hosts, die nicht (mehr) in ``hostnames`` stehen."""
        keep = {h.lower() for h in hostnames}
        with db_lock:
            conn = self.connect_db()
            cursor = conn.cursor()
            cursor.execute(f"SELECT DISTINCT hostname FROM [{self.table_name}]")
            stale = [row[0] for row in cursor.fetchall() if (row[0] or '').lower() not in keep]
            for host in stale:
                cursor.execute(f"DELETE FROM [{self.table_name}] WHERE hostname = ?", host)
            conn.commit()
        if stale:
            self.logger.info(f"Removed records of hosts no longer in host list: {stale}")
        return len(stale)

    def delete_inventory(self):
        """Löscht alle Einträge aus der Inventartabelle."""
        with db_lock:
            conn = self.connect_db()
            conn.execute(f"DELETE FROM [{self.table_name}]")
            conn.commit()
        self.logger.warning(f"All records in {self.table_name} deleted")
