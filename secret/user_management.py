import hashlib
import hmac
from getpass import getpass

from secret.pwd_management import USER_DETAILS_FILEPATH
from secret.pwd_management import hash_password, INVALID_PASSWORD_ERROR, DEFAULT_PASSWORD_LENGTH

roles = ["administrator", "user"]

def save_user(username, hashed_pwd):
    """
    Save user information to users detail file.

    :param username:
    :param hashed_pwd:
    :return:
    """
    with open(USER_DETAILS_FILEPATH, 'a') as f:
        f.write(f"{username} {hashed_pwd}\n")

def _find_user(username):
    """Liefert den gespeicherten ``salt$hash``-Wert des Benutzers oder ``None``."""
    try:
        with open(USER_DETAILS_FILEPATH, 'r') as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 2 and parts[0] == username:
                    return parts[1]
    except FileNotFoundError as fl_err:
        print(f"{fl_err.args[-1]}: {USER_DETAILS_FILEPATH}")
    return None


def user_exists(username):
    return _find_user(username) is not None


def user_auth(username, password):
    stored = _find_user(username)
    if not stored or '$' not in stored:
        return False

    # Hash the input password with the same salt
    salt, stored_hash = stored.split('$', 1)
    input_hash = hashlib.sha256((salt + password).encode('utf-8')).hexdigest()
    return hmac.compare_digest(input_hash, stored_hash)

'''password_test = "password123"
salt = "randomsaltvalue"
hashed_pwd = hashlib.sha256(password_test.encode('utf-8') + salt.encode('utf-8')).hexdigest()'''

def validate_input(password_length):
    try:
        password_length = int(password_length)
        if password_length < 12 or password_length > 24:
            raise ValueError("Password length must be between 12 and 24")
        return password_length
    except ValueError:
        print(INVALID_PASSWORD_ERROR)
        return DEFAULT_PASSWORD_LENGTH

def register(username, password):

    ### if user_role == "administrator":
    if user_exists(username):
        print(f"User {username} already exists")
        return
    length = input("Enter password length: ")
    length = validate_input(length)
    # password = generate_password(length)

    hashed_passwd = hash_password(password)
    save_user(username, hashed_passwd)
    print(f"User {username} registered")
    print(f"Your password is {password}")

def login():
    username = input("Enter username: ")
    if not user_exists(username):
        print("User does not exist.")
        return

    password = getpass("Password: ")
    if not user_auth(username, password):
        print("Incorrect password.")
        return
    print("Login successful.")