import configparser


def get_config():
    config = configparser.ConfigParser()
    config.read('config\\config.ini')

    return {
        'db_config': {
            'hostname': config.get('database', 'hostname'),
            'username': config.get('database', 'username'),
            'password': config.get('database', 'password'),
            'database': config.get('database', 'database'),
            'table_name': config.get('database', 'table_name')
        }
    }