import logging

import eel
from serial.tools import list_ports

from usbl_driver import USBLController

eel.init('web')
logger = logging.getLogger()
logger.setLevel(logging.INFO)


class AppLoggingHandler(logging.Handler):
    def emit(self, record: logging.LogRecord):
        try:
            eel.add_to_log(record.msg)
        except AttributeError:
            pass


my_handler = AppLoggingHandler()
logger.addHandler(my_handler)


# wrap since this callback is not yet ready.
def change_observer(*args, **kwargs):
    eel.on_controller_attr_changed(*args, **kwargs)


usbl_controller = USBLController(change_observer)


def controller_set_attr(k, v):
    try:
        setattr(usbl_controller, k, v)
    except Exception as e:
        logger.error(f"Failed to set {k} to {v}: {e}")
        raise


def poll_usb_devices_thread():
    while True:
        port_names = []
        try:
            for cp in list_ports.comports():
                port_names.append(cp.device)
            port_names.append('/dev/debug')
            eel.on_list_usb_devices(port_names)
        except Exception as e:
            print(e)
        eel.sleep(3.0)


eel.expose(controller_set_attr)

eel.spawn(poll_usb_devices_thread)
eel.start('main.html')
print('eel loop ended')
