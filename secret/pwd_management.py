# -*- coding: utf-8 -*-

import hashlib
import os
import secrets
import string

USER_DETAILS_FILEPATH = ".\\users.txt"
PUNCTUATIONS = '!"§$%&@€#-_'

DEFAULT_PASSWORD_LENGTH = 12

INVALID_PASSWORD_ERROR =    f'''
                            Password length must be between 12 and 24.
                            Password length must be a number.
                            Generating password with default length of {DEFAULT_PASSWORD_LENGTH} characters.
                            '''

'''def generate_password(length=DEFAULT_PASSWORD_LENGTH):
    """
    Generate password with given length.

    :param length:
    :return:
    """
    chars = string.ascii_letters + string.digits + PUNCTUATIONS
    pwd = ''.join(secrets.choice(chars) for _ in range(length))
    return pwd'''

def hash_password(pwd):
    """
    Hash password using sha256 hashing algorithm with salt.

    :param pwd:
    :return:
    """

    # Generate random salt
    salt = os.urandom(16).hex()

    # Combine salt and pass, then hash
    pwd_bytes = (salt + pwd).encode('utf-8')
    hashed_pwd = hashlib.sha256(pwd_bytes).hexdigest()
    return f"{salt}${hashed_pwd}"