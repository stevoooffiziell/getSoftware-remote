import tkinter as tk
from tkinter import messagebox
import secret.user_management as um


def gui_login():
    username = entry_username.get()
    password = entry_password.get()

    if not um.user_exists(username):
        messagebox.showerror("Error", "Username does not exist")
        '''entry_username.delete(0, "end")
        entry_password.delete(0, "end")''' # Removes content from Entry object
        return

    if um.user_auth(username, password):
        messagebox.showinfo("Success", "Logged in successfully")
        del password
        '''entry_username.delete(0, "end")
        entry_password.delete(0, "end")''' # Removes content from Entry object
    else:
        messagebox.showerror("Error", "Incorrect Password")
        '''entry_password.delete(0, "end")''' # Removes content from Entry object

def gui_register():
    username = entry_username.get()
    if um.user_exists(username):
        messagebox.showerror("Error", "Username already exists")
        '''entry_password.delete(0, "end")''' # Removes content from Entry object
        return

    password = entry_password.get()
    hashed_passwd = um.hash_password(password)
    # Write User data to db
    um.save_user(username, hashed_passwd)

    # Deletes local variables
    del password, hashed_passwd

    messagebox.showinfo("Success", "Registered successfully")

root = tk.Tk()
root.title("Login - The Useless Five")

frame = tk.Frame(root, padx=20, pady=20)
frame.pack()

lbl_username = tk.Label(frame, text="Username")
lbl_username.grid(row=0, column=0, sticky="w")
entry_username = tk.Entry(frame)
entry_username.grid(row=0, column=1)

lbl_password = tk.Label(frame, text="Password:")
lbl_password.grid(row=1, column=0, sticky="w")
entry_password = tk.Entry(frame, show="*")
entry_password.grid(row=1, column=1)

btn_login = tk.Button(frame, text="Login", command=gui_login)
btn_login.grid(row=2, column=0, pady=10)

btn_register = tk.Button(frame, text="Register", command=gui_register)
btn_register.grid(row=2, column=1, pady=10)

root.mainloop()