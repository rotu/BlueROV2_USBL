from typing import Optional, BinaryIO

import PySimpleGUI as sg
import tkinter

import serial
from serial.tools import list_ports

from usbl_driver import USBLController


def get_device_names():
    return sorted([cp.device for cp in list_ports.comports()])


# gps_combo = sg.Combo([])
# # All the stuff inside your window.
# layout = [
#     [sg.Text('GPS device', size=(15, 1)), gps_combo],
#     [sg.Text('USBL device', size=(15, 1)), sg.Combo(get_device_names(),
#     default_value='/dev/bar')],
#     [sg.Text('ROV Address', size=(15, 1)), sg.InputText('192.168.2.2:27000')],
#     [sg.Button('Start'), sg.Button('Exit')],
# ]
# # Create the Window

from tkinter import *
from tkinter.ttk import Combobox

root = Tk()
dev_gps = tkinter.StringVar()
dev_gps.set('/dev/ttyACM0')
gps_active = tkinter.BooleanVar()

dev_usbl = tkinter.StringVar()
dev_usbl.set('/dev/ttyUSB0')
usbl_active = tkinter.BooleanVar()

addr_rov = tkinter.StringVar()
addr_rov.set('192.168.2.2:27000')
rov_active = tkinter.BooleanVar()

addr_gps_echo = tkinter.StringVar()
addr_gps_echo.set('localhost:14401')
gps_echo_active = tkinter.BooleanVar()

controller = USBLController()


def toggle_all():
    pass


def foo(*args):
    pass


Label(root, text='GPS Device:', justify=RIGHT).grid(sticky=E, column=0, row=0)
Combobox(root, values=get_device_names(), textvariable=dev_gps).grid(column=1, row=0)


def toggle_gps():
    if gps_active.get():
        new_dev = dev_gps.get()
    else:
        new_dev = None
    if gps_active.get():
        try:
            controller.set_dev_gps(new_dev)
        except Exception:
            gps_active.set(False)
            raise


gps_cb = Checkbutton(root, text='', variable=gps_active)
gps_cb.configure(command=toggle_gps)
gps_cb.grid(column=3, row=0)

# gps_active.trace_add('write', toggle_gps)

Label(root, text='USBL Device:', justify=RIGHT).grid(sticky=E, column=0, row=1)
Combobox(root, values=get_device_names(), textvariable=dev_usbl).grid(column=1, row=1)
Checkbutton(root, text='', variable=usbl_active).grid(column=3, row=1)

Label(root, text='ROV Address:', justify=RIGHT).grid(sticky=E, column=0, row=2)
Entry(root, textvariable=addr_rov).grid(column=1, row=2)
Checkbutton(root, text='', variable=rov_active).grid(column=3, row=2)

Label(root, text='Echo GPS to:').grid(sticky=E, column=0, row=3)
Entry(root, textvariable=addr_gps_echo).grid(column=1, row=3)
Checkbutton(root, text='', variable=gps_echo_active).grid(column=3, row=3)

Button(root, text='all', command=toggle_all).grid(column=3, row=4)


def greet():
    print(dev_gps.get())
    print(dev_usbl.get())
    print("Greetings!")


root.winfo_toplevel().title('USBL Relay')
root.attributes('-topmost', True)
root.mainloop()
