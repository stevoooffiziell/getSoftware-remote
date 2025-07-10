import configparser


def get_config():
    config = configparser.ConfigParser()
    config.read('config/web_config.ini')

    return {
        'inventory_interval': config.getint('scheduler', 'interval_weeks', fallback=2),
        'db_config': {
            'hostname': config.get('database', 'hostname'),
            'username': config.get('database', 'username'),
            'password': config.get('database', 'password'),
            'database': config.get('database', 'database'),
            'table_name': config.get('database', 'table_name')
        }
    }