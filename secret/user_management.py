import hashlib
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

def user_exists(username):
    try:
        with open(USER_DETAILS_FILEPATH, 'r') as f:
            for line in f:
                parts = line.split()
                if parts[0] == username:
                    return True
    except FileNotFoundError as fl_err:
        print(f"{fl_err.args[-1]}: {USER_DETAILS_FILEPATH}")
        print(f"System will create file: {USER_DETAILS_FILEPATH}")
    return False

def user_auth(username, password):
    try:
        with open(USER_DETAILS_FILEPATH, 'r') as f:
            for line in f:
                parts = line.split()
                if parts[0] == username:
                    # Split salt and hash from stored value
                    salt, stored_hash = parts[1].split('$')

                    # Hash the input password with the same salt
                    pwd_bytes = (salt + password).encode('utf-8')
                    input_hash = hashlib.sha256(pwd_bytes).hexdigest()

                    if input_hash == stored_hash:
                        return True
                    else:
                        return False
                return False
    except FileNotFoundError as fl_err:
        print(f"{fl_err.args[-1]}: {USER_DETAILS_FILEPATH}")

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