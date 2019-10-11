#!/usr/bin/python3
import json
import logging
from functools import wraps

import webview
from serial.tools import list_ports

from usbl_driver import USBLController

logger = logging.getLogger()
logger.setLevel(logging.INFO)

usbl_controller = USBLController()


class Api:
    def controller_set_attr(self, obj):
        (attr, value), = obj.items()
        print(f'setting {attr}={value}')

        try:
            setattr(usbl_controller, attr, value)
        except Exception as e:
            logger.error(str(e))

        ## in pywebview, return values from Python don't work reliably
        # return getattr(usbl_controller, attr)

    def get_serial_devices(self, *arg, **kwargs):
        try:
            result = [cp.device for cp in list_ports.comports()]
            result.append('/dev/debug')
            return result
        except Exception as e:
            add_to_log('error', str(e))


window = webview.create_window('USBL controller', url='web/main.html', js_api=Api())


def js_function(stub: callable):
    """Decorator for a function whose implementation actually lives in Python"""

    @wraps(stub)
    def wrapper(*args, **kwargs):
        assert not args or not kwargs
        if kwargs:
            argstr = json.dumps(kwargs)
        else:
            argstr = ','.join(json.dumps(a) for a in args)
        snippet = f'{stub.__name__}({argstr})'
        return window.evaluate_js(snippet)

    return wrapper


@js_function
def add_to_log(severity, message): ...


@js_function
def on_controller_attr_changed(attr, value): ...


@js_function
def on_list_usb_devices(values): ...


class AppLoggingHandler(logging.Handler):
    def emit(self, record: logging.LogRecord):
        add_to_log(record.levelname.lower(), record.msg)


my_handler = AppLoggingHandler()
logger.addHandler(my_handler)

usbl_controller.set_change_callback(on_controller_attr_changed)

webview.start(http_server=True, debug=True)
