#!/usr/bin/python3
import logging
from threading import Thread

import eel
import webview
from serial.tools import list_ports

from usbl_driver import USBLController

eel.init('web')
logger = logging.getLogger()
logger.setLevel(logging.INFO)


class AppLoggingHandler(logging.Handler):
    def emit(self, record: logging.LogRecord):
        try:
            eel.add_to_log(record.levelname.lower(), record.msg)
        except AttributeError:
            pass


my_handler = AppLoggingHandler()
logger.addHandler(my_handler)


# wrap since this callback is not yet ready.
def change_observer(*args, **kwargs):
    eel.on_controller_attr_changed(*args, **kwargs)


usbl_controller = USBLController(change_observer)


def controller_set_attr(k, v):
    logger.info(f'setting attr {k}={v}')
    try:
        setattr(usbl_controller, k, v)
    except Exception as e:
        logger.error(f"Failed to set {k} to {v}: {e}")


def get_serial_devices():
    while True:
        port_names = []
        try:
            for cp in list_ports.comports():
                port_names.append(cp.device)
            port_names.append('/dev/debug')
            eel.on_list_usb_devices(sorted(port_names))
        except Exception as e:
            logger.error(e)


eel.expose(controller_set_attr)
eel.expose(get_serial_devices)

webview.create_window('USBL controller', 'http://localhost:8000/main.html')
eel.start(options={'host': 'localhost', 'port': 8000,
    'mode': None},block=False)
# eel_thread = Thread(target=eelambda)
# eel_thread.start()

webview.start(gui='qt')
# eel_thread.join()
