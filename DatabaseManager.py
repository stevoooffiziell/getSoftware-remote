import re
import logging
import os
import time
from os.path import exists

import pyodbc
import configparser
from datetime import datetime
from cryptography.fernet import Fernet


def welcome():
    print("######################################################################################################\n"
          "#                                                                                                    #\n"
          "#                              Welcome to the network software service!                              #\n"
          "#                                                                                                    #\n"
          "#----------------------------------------------------------------------------------------------------#\n"
          "#                                                                                                    #\n"
          "# This script will identify all installed software which has been installed with a regular installer #\n"
          "#                       To start the script read this documentation carefully.                       #\n"
          "#                                                                                                    #\n"
          "######################################################################################################\n"
          "# Step 1: Make sure the template_hosts.csv is renamed to hosts.csv and contains IP adresses or       #\n"
          "#         hostnames otherwise the script wont start                                                  #\n")
    time.sleep(10)


welcome()


class DatabaseManager:
    def __init__(self, config_file="config\\config.ini"):
        self.info = "[INFO]    |"
        self.debug = "[DEBUG]   |"
        self.warning = "[WARNING] |"
        self.error = "[ERROR]   |"

        def get_logprint_info(): return f"{get_timestamp('')} | {self.info}"

        def get_logprint_error(): return f"{get_timestamp('')} | {self.error}"

        def get_logprint_debug(): return f"{get_timestamp('')} | {self.debug}"

        def get_logprint_warning(): return f"{get_timestamp('')} | {self.warning}"

        self.get_logprint_info = get_logprint_info
        self.get_logprint_debug = get_logprint_debug
        self.get_logprint_warning = get_logprint_warning
        self.get_logprint_error = get_logprint_error

        self.config_file = config_file

        self.time_dmy = get_timestamp("dmy")
        self.time_hms = get_timestamp("hms")
        self.log_file = f'logs\\{self.time_dmy}_{self.time_hms}-dbmanager.log'
        os.makedirs(os.path.dirname(self.log_file), exist_ok=True)

        # Configure Logger
        self.logger = logging.getLogger(__name__)
        if not self.logger.handlers:
            file_handler = logging.FileHandler(self.log_file)
            formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
            file_handler.setFormatter(formatter)
            self.logger.addHandler(file_handler)

        config = configparser.ConfigParser()
        config.read(config_file)

        self.existing_config = exists("config\\config.ini")

        self.conn = None

    def _initialize_db_connection(self, config_file):
        """
        Initializes the database connection.
        Function reads the ``config_file`` and initializes the connection to the given database.
        """
        try:
            config = configparser.ConfigParser()
            config.read(config_file)

            encrypted_pwd_db = config.get('db', 'pass')
            self.pwd = decrypt_password(encrypted_pwd_db)

            self.host = config.get('db', 'host')
            self.user = config.get('db', 'user')
            self.db = config.get('db', 'database')
            self.driver = config.get('db', 'driver')
            self.connection_str = (
                f"DRIVER=" + "{" + f"{self.driver}" + "}" + f";"
                                                            f"SERVER={self.host},1433;"
                                                            f"DATABASE={self.db};"
                                                            f"UID={self.user};"
                                                            f"PWD={self.pwd};"
                                                            f"TrustServerCertificate=yes;"
                                                            f"Authentication=SqlPassword;"
            )

            self.backup_table = config.get('db', 'backup-table')
            self.table_name = config.get('db', 'prod-table')

            self.connect_db()

        except Exception as e:
            self.logger.error(f"Initialization error: {e}")
            raise

    def connect_db(self):
        """
        Connects the service to the database.
        :return:
        """

        try:
            if self.driver not in ["ODBC Driver 17 for SQL Server", "ODBC Driver 18 for SQL Server"]:
                raise ValueError(f"Unsupported driver. {self.driver}")

            self.conn = pyodbc.connect(self.connection_str)
            self.logger.info("Database connection established successfully.")
            self.logger.info("Driver configuration is correct.")
            print(f"{self.get_logprint_info()} Driver configuration is correct.")
            print(f"{self.get_logprint_info()} Connection to database {self.db} established.")

        except Exception as e:
            self.logger.error(f"The driver '{self.driver}' is not supported by this SQL-Server\n"
                              f"Connection error: {str(e)}")
            self.logger.error(f"Exiting program now...")
            print(f"{self.get_logprint_error()} The driver {self.driver} is not supported by this SQL-Server\n"
                  f"{self.get_logprint_error()} For more information read the log: {self.log_file}\n"
                  f"{self.get_logprint_error()} Exiting program now...\n")
            raise

    def dependencies_check(self):
        """

        :return:
        """
        if self.existing_config:
            print(f"{self.get_logprint_info()} Configuration file is set.")
            self.logger.info("Test")
        else:
            print(f"{self.get_logprint_error()} Config file is not in the expected directory!")
            self.logger.error("Config file is not in the expected directory!")
            exit()

    def db_disconnect(self):
        """

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

    def insert_software(self, software_list, hostname):
        """
        Insert the values from the gathered JSON file into the database

        ``query`` is declared as a local variable. It's not dynamic at this point, but it will be in the future
        :var self.query:
        :param software_list:
        :param hostname:
        :return:
        """

        query = f"""
        INSERT INTO [{self.table_name}] (name, publisher, installDate, programSize, version, hostname, isNew)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """

        try:
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

                check_table_backup = queries(self.backup_table)
                check_table = queries(self.table_name)

                if not self.conn.execute(check_table):
                    print("Wenn kein Wert, dann Fehler")

                self.conn.execute(check_table_backup)

                if self.conn.commit():
                    print("Datenbanktabelle existiert bereits. Überspringe...")

                if publisher_str.startswith("Interflex"):
                    publisher_str = "Interflex Datensysteme GmbH & Co. KG"
                    cursor.execute(query, (
                        item.get('Name'),
                        publisher_str,
                        install_date,
                        item.get('Size'),
                        item.get('Version'),
                        hostname,
                        0
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
                        0
                    ))
                    self.conn.commit()

            print(f"{self.get_logprint_info()} Software-list has been written into database {self.db}")
            self.logger.info(f"Software-list has been written into database {self.db}")

        except Exception as e:
            self.conn.rollback()
            print(f"An Error has occured while inserting data into database: {e}")
            self.logger.error(f"An Error has occured while inserting data into database: {e}")

    def backup_database_table(self):
        """

        :return:
        """
        copy_query = f"""
            INSERT INTO {self.backup_table} (name, publisher, installDate, programSize, hostname, isNew)
            SELECT name, publisher, installDate, programSize, hostname, isNew
            FROM {self.table_name}
            WHERE isNew = 0
            """

        try:
            self.conn.execute(queries(self.table_name))
            self.conn.commit()
            print(f"{self.get_logprint_info()} Productive table {self.table_name} has been successfully created!")
            self.logger.info(f"Productive table {self.table_name} has been successfully created!")
        except pyodbc.Error as e:
            print(f"Error during creating table {self.table_name}")
            self.logger.error(f"Error during creating table {self.table_name}")
            raise RuntimeError from e

        try:
            self.conn.execute(queries(self.backup_table))
            self.conn.commit()
            print(f"{self.get_logprint_info()} Backup table {self.backup_table} has been successfully created!")
            self.logger.info(f"Backup table {self.backup_table} has been successfully created!")
        except pyodbc.Error as e:
            print(f"Error during creating table {self.backup_table}")
            self.logger.error(f"Error during creating table {self.backup_table}")
            raise RuntimeError from e

    def reset_data_table(self):
        """

        :return:
        """
        if not Exception:
            # Defined SQL-Query to update all old entries to keep track of the new and old data
            # TODO: Add Exception Handling, to stop the script.
            #  Before updating data add a backup (just in case to be safe)
            update_table = f"UPDATE {self.table_name} SET isNew = 1;"
            try:
                # Execute the code
                self.conn.commit()
                self.conn.execute(update_table)
                print(f"The update of the old data values in {self.table_name} has been set successfully")
            except Exception as e:
                print(f"[ERROR] The script ran into an error: {e}")
                quit()


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


def get_timestamp(format_var):
    """
    Supportive function for timestamp in custom formatting

    ``format_var`` == "dmy" output = ``01-01-1970``

    ``format_var`` == "hms" output = ``12-30-22``

    :param format_var:
    :return: str
    """
    if format_var == "dmy":
        timestamp = datetime.now().strftime("%d-%m-%Y")
        return timestamp
    elif format_var == "hms":
        timestamp = datetime.now().strftime("%H-%M-%S")
        return timestamp
    return datetime.now().strftime("%d-%m-%Y %H-%M-%S")


def decrypt_password(encrypted_password: str, key_path: str = "config\\secret.key") -> str:
    """
    Uses the ``secret.key`` to decrypt the previously encrypted password.

    ``key_path`` folder path where the secret.key is located

    :param encrypted_password:
    :param key_path:
    :return: str
    """

    with open(key_path, "rb") as key_file:
        key = key_file.read()
    fernet = Fernet(key)
    return fernet.decrypt(encrypted_password.encode()).decode()


log = DatabaseManager()
log.dependencies_check()
