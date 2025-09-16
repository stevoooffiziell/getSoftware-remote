# -*- coding: utf-8 -*-

# IGNORE THIS, ONLY TEST PURPOSES XD

'''
from secret.user_management import register, login
from secret.pwd_management import USER_DETAILS_FILEPATH

def main():
    while True:
        print("1. Register\n2. Login\n3. Exit")
        choice = input("Enter your choice: ")
        if choice == "1":
            username = input("Enter your username: ")
            with open(USER_DETAILS_FILEPATH, "r") as file:
                for line in file:
                    if username in line[0]:
                        user_details = line.strip().split(" ")
                        if user_details[0] == username:
                            print("Username already registered.")

            register(username)
        elif choice == "2":
            login()
        elif choice == "3":
            break
        else:
            print("Invalid choice.")

if __name__ == "__main__":
    main()
'''
