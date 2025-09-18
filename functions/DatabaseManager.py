# -*- coding: utf-8 -*-

import re
import logging
import os
import threading

import pyodbc
import configparser
from datetime import datetime
from cryptography.fernet import Fernet

db_lock = threading.Lock()


def clean_names(item):
    # Architektur in Klammern entfernen (z.B. (x64), (64-bit), (x86_64))
    name = re.sub(r'\(\s*.*?(x64|x86|64-bit|32-bit|x86_64).*?\s*\)', '', item, flags=re.IGNORECASE)
    # Architektur-Begriffe außerhalb von Klammern entfernen (inkl. Unterstrich)
    name = re.sub(r'\b(x64|x86|64-bit|32-bit|x86_64)\b', '', name, flags=re.IGNORECASE)
    # Versionen entfernen, z.B. "14.40.33816", "v11.10"
    name = re.sub(r'\bv?\d+(\.\d+)*\b', '', name, flags=re.IGNORECASE)
    # Leere Klammern entfernen
    name = re.sub(r'\(\s*\)', '', name)
    # Leerzeichen um Bindestriche bereinigen, Jahresbereiche wie 2015-2022 bleiben
    name = re.sub(r'(?<=\D)\s*-\s*(?=\D)', '-', name)
    # Leerzeichen und Bindestriche am Ende entfernen
    name = re.sub(r'[\s\-]+$', '', name)
    # Mehrere Leerzeichen auf eins reduzieren
    name = re.sub(r'\s{2,}', ' ', name)
    name = name.strip()
    return name


class DatabaseManager:
    _instance = None
    _initialized = False

    def __new__(cls, *args, **kwargs):
        """
        Singleton-Pattern: Ensures that the instance exists only once

        :param args:
        :param kwargs:
        """
        if not cls._instance:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, config_file = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "config", "config.ini")), transport='ntlm'):
        """
        Initializes database connection only once

        Needs the parameter ``config_file``

        :param config_file:
        """
        if self._initialized:
            return
        self.config_file = config_file
        config = configparser.ConfigParser()
        read_files = config.read(self.config_file)
        if not read_files:
            raise FileNotFoundError(f"Config file not found: {self.config_file}")

        if not config.has_section('db'):
            raise Exception("Config file does not have [db] section")

        self.pwd = config.get('db', 'pass')

        self.host = config.get('db', 'host', fallback='10.100.13.55')
        self.user = config.get('db', 'user', fallback='db-admin')
        self.db = config.get('db', 'database')
        self.driver = config.get('db', 'driver')

        self.passw = decrypt_password(self.pwd)


        connection_str =(
                f"DRIVER=" + "{" + f"{self.driver}" + "}" + f";"
                                                            f"SERVER={self.host},1433;"
                                                            f"DATABASE={self.db};"
                                                            f"UID={self.user};"
                                                            f"PWD={self.passw};"
                                                            f"TrustServerCertificate=yes;"
                                                            f"Authentication=SqlPassword;"
        )
        self.connection_str = connection_str

        self.backup_table = config.get('db', 'backup-table')
        self.table_name = config.get('db', 'prod-table')

        # Zeitstempel für Logs
        self.time_dmy = self.get_timestamp("dmy")
        self.time_hms = self.get_timestamp("hms")

        # Initialize Logger
        print(f"{self.get_timestamp('')} | [INFO]    | Initializing logger...")
        self._init_logger()

        # Konfiguration
        self.info = "[INFO]    |"
        self.debug = "[DEBUG]   |"
        self.warning = "[WARNING] |"
        self.error = "[ERROR]   |"
        self.config_file = config_file
        self.existing_config = os.path.exists(config_file)
        self.conn = None

        # Database-configuration
        self._load_config()
        self._initialize_db_connection()
        self._ensure_metadata_table()
        self._initialized = True
        self.logger.info("DatabaseManager initialized")
        print(f"{self.get_logprint_info()} Database connection established.")

    def _init_logger(self):
        self.log_file = os.path.join('../logs', f'{self.time_dmy}_{self.time_hms}-dbmanager.log')
        os.makedirs(os.path.dirname(self.log_file), exist_ok=True)

        self.logger = logging.getLogger('DatabaseManager')
        self.logger.setLevel(logging.INFO)

        # Add only one Handler if none exists
        if not self.logger.handlers:
            file_handler = logging.FileHandler(self.log_file)
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            file_handler.setFormatter(formatter)
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

    def _load_config(self):
        try:
            config = configparser.ConfigParser()
            config.read(self.config_file)
            self.logger.info("Configuration loaded successfully")
        except Exception as e:
            self.logger.error(f"Error loading configuration: {str(e)}")
            raise RuntimeError(f"Configuration error: {str(e)}")

    def _initialize_db_connection(self):
        """
        Initializes the database connection.
        Function reads the ``config_file`` and initializes the connection to the given database.
        """
        available_drivers = ["ODBC Driver 17 for SQL Server", "ODBC Driver 18 for SQL Server"]


        try:
            self.conn = pyodbc.connect(self.connection_str)
            if self.conn:
                try:
                    # Prüfe ob Verbindung noch gültig
                    self.conn.execute("SELECT 1")
                    self.logger.info("Using existing database connection")
                    return
                except pyodbc.Error:
                    self.logger.warning("Existing connection invalid, reconnecting...")
                    self.conn = None

            if not self.driver:
                raise ValueError("Database driver not configured")

            if self.driver not in available_drivers:
                raise ValueError(
                    f"Driver '{self.driver}' not installed. Available drivers: {available_drivers}")

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
        """
        Ensures that the table exists in the database

        :return:
        """
        try:
            create_table_sql = """
            IF NOT EXISTS (
                SELECT * FROM INFORMATION_SCHEMA.TABLES 
                WHERE TABLE_NAME = 'service_metadata'
            )
            BEGIN
                CREATE TABLE service_metadata (
                    service_active INT,
                    last_inventory_start DATETIME,
                    next_inventory_start DATETIME,
                    interval_weeks INT,
                    last_end_time DATETIME,
                    identifier INT
                );
                
                DECLARE @init_last_run DATETIME = NULL;
                DECLARE @init_next_run DATETIME = DATEADD(WEEK, 2, GETDATE());
        
                INSERT INTO service_metadata (
                    service_active, 
                    last_inventory_start, 
                    next_inventory_run, 
                    interval_weeks,
                    last_end_time,
                    identifier
                ) VALUES (
                    0,
                    @init_last_run,
                    @init_next_run,
                    2,
                    NULL,
                    NULL
                );
            END
            """
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
        Stellt sicher, dass eine gültige DB-Verbindung besteht

        :return:
        """
        if self.conn is None:
            self._initialize_db_connection()
        return self.conn

    def dependencies_check(self):
        """
        Checks if a configuration file is existing

        :return:
        """
        if self.existing_config:
            self.logger.info("Configuration file verified")
            print(f"{self.get_logprint_info()} Configuration file is set.")
        else:
            self.logger.error("Config file missing")
            print(f"{self.get_logprint_error()} Config file is not in the expected directory!")
            raise FileNotFoundError("Configuration file missing")

    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        context manager: disconnect automatically

        :param exc_type:
        :param exc_val:
        :param exc_tb:
        :return:
        """
        try:
            self.conn.close()
            self.logger.info(f"Connection to database {self.db} has been closed successfully.")
            print(f"{self.get_logprint_info()} Connection to database {self.db} has been closed successfully")
        except Exception as e:
            self.logger.error(f"The connection to the database {self.db} hasn't been closed successfully!")
            self.logger.error(f"Error description: {e}")
            print(
                f"{self.get_logprint_error()} The connection to the database {self.db} hasn't been closed successfully!")
            print(f"{self.get_logprint_error()} An unknown error has occured: {e}")

    def ensure_tables_exist(self):
        """
        ensures that required tables exist

        :return: Any
        """
        try:
            with db_lock:
                # productive table
                self.conn.execute(queries(self.table_name))
                self.logger.info(f"Checked/Created table {self.table_name}")

                self.conn.commit()

                # backup table TODO: implement it or abandon it? Or get a better solution. Create a backup SQL-file?
                #                    Makes sense to me tho.
                '''self.conn.execute(queries(self.backup_table))
                self.logger.info(f"Checked/Created table {self.backup_table}")'''

                self.conn.commit()

        except Exception as e:
            self.logger.error(f"Table creation failed: {str(e)}")
            raise

    def get_metadata(self, key):
        """
        Holt einen Metadaten-Wert aus der Datenbank

        :param key:
        :return:
        """
        try:
            self.connect_db()
            cursor = self.conn.cursor()
            cursor.execute(f"SELECT {key} FROM service_metadata WHERE identifier = 1")
            row = cursor.fetchone()
            if row:
                return row[0]
        except Exception as e:
            self.logger.error(f"Error getting metadata for key '{key}': {str(e)}")
            return None

    def set_metadata(self, key, value):
        """Setzt einen Metadaten-Wert in der Datenbank"""
        try:
            if self.get_metadata(key):
                self.conn.execute(f"UPDATE service_metadata SET {key} = {value} WHERE identifier = 1")
                self.conn.commit()
            else:
                self.conn.execute(f"INSERT INTO service_metadata {key} VALUES ({value})")
                self.conn.commit()
            self.logger.info(f"Metadata updated: {key} = {value}")
            print(f"Metadata updated: {key} = {value}")
            return True
        except Exception as e:
            self.logger.error(f"Error setting metadata for key '{key}': {str(e)}")
            return False

    def set_starttime(self):
        cursor = self.conn.cursor()
        x = datetime.now()
        cursor.execute("UPDATE service_metadata SET last_inventory_start = ? WHERE identifier = 1", x)
        cursor.commit()
        return print(f"Metadata has been updated to: {x}")

    def set_nexttime(self, value):
        cursor = self.conn.cursor()
        cursor.execute("UPDATE service_metadata SET next_inventory_run = ? WHERE identifier = 1", value)
        cursor.commit()
        return print(f"Metadata 'next_inventory_run' has been updated to: {value}")

    def insert_software(self, software_list, hostname):
        """
        Insert the values from the gathered JSON file into the database

        ``query`` is declared as a local variable. It's not dynamic at this point, but it will be in the future
        :var self.query:
        :param software_list:
        :param hostname:
        :return:
        """

        try:
            with db_lock:  # Thread-security
                # Need to reconnect?
                self.connect_db()
                # Ensure that tables exist
                # self.ensure_tables_exist()

                query = f"""
                        INSERT INTO [{self.table_name}] (name, publisher, installDate, programSize, version, hostname, isNew)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """

                insert_count = 0

                for item in software_list:
                    name = item.get('Name') or 'Unknown'
                    publisher = item.get('Publisher') or ''
                    install_date_str = item.get('InstallDate')
                    size = item.get('Size') or 0
                    version = item.get('Version') or '0.0.0'
                    # process installDate
                    install_date = None
                    if install_date_str := item.get('InstallDate'):
                        try:
                            # support different time formats
                            for fmt in ("%Y%m%d", "%Y-%m-%d", "%d.%m.%Y"):
                                try:
                                    install_date = datetime.strptime(install_date_str, fmt).date()
                                    break
                                except ValueError:
                                    continue
                        except Exception:
                            install_date = None

                    # unification same publisher with different spelling
                    publisher = str(item.get('Publisher', ''))
                    if "Interflex" in publisher:
                        publisher = "Interflex Datensysteme GmbH & Co. KG"
                    if "Microsoft" in publisher:
                        publisher = "Microsoft Corporation"


                    name = clean_names(item.get('Name'))

                    # insert data
                    self.conn.execute(query, (
                        name,
                        publisher[:90],  # Auf maximale Länge kürzen
                        install_date,
                        size,
                        version[:50],
                        hostname,
                        True  # isNew = True
                    ))
                    insert_count += 1

                self.conn.commit()
                self.logger.info(f"Inserted {insert_count} records for {hostname}")
                print(f"{self.get_logprint_info()} Inserted {insert_count} items for {hostname}")

        except Exception as e:
            self.logger.error(f"Insert failed for {hostname}: {str(e)}")
            if self.conn:
                self.conn.rollback()
            raise

    '''def backup_database_table(self):
        """

        :return:
        """
        try:
            with db_lock:
                self.ensure_tables_exist()

                copy_query = f"""
                        INSERT INTO {self.backup_table} (name, publisher, installDate, programSize, version, hostname, isNew)
                        SELECT name, publisher, installDate, programSize, version, hostname, isNew
                        FROM {self.table_name}
                        """

                self.conn.execute(copy_query)
                self.conn.commit()

                self.logger.info(f"Backup created in {self.backup_table}")
                print(f"{self.get_logprint_info()} Backup created successfully")

        except Exception as e:
            self.logger.error(f"Backup failed: {str(e)}")
            if self.conn:
                self.conn.rollback()
            raise'''

    '''def reset_data_table(self):
        """

        :return:
        """
        try:
            with db_lock:
                self.connect_db()

                update_query = f"UPDATE {self.table_name} SET isNew = 1;"

                self.conn.execute(update_query)
                self.conn.commit()

                self.logger.info("Reset isNew flags")
                print(f"{self.get_logprint_info()} Reset completed")

        except Exception as e:
            self.logger.error(f"Reset failed: {str(e)}")
            if self.conn:
                self.conn.rollback()
            raise'''


def queries(table):
    """
    Generates sql-query. Creates a new table if the given name is not existing

    :param table:
    :return: ``str``
    """
    # Ensure that the table name is valid
    if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', table):
        raise ValueError(f"Invalid table name: {table}")

    query = f"""
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
    return query

def decrypt_password(encrypted_password: str, key_path: str = "config\\secret.key") -> str:
    """
    Uses the ``secret.key`` to decrypt the previously encrypted password.

    ``key_path`` folder path where the secret.key is located

    :param encrypted_password:
    :param key_path:
    :return: str
    """

    try:
        with open(key_path, "rb") as key_file:
            key = key_file.read()
        fernet = Fernet(key)
        return fernet.decrypt(encrypted_password.encode()).decode()
    except Exception as e:
        logging.error(f"Decryption failed: {str(e)}")
        raise RuntimeError("Password decryption error")
