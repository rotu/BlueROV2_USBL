#!/usr/bin/python3
import json
import logging
from functools import wraps

import webview
from serial.tools import list_ports

from usbl_driver import USBLController

usbl_controller = USBLController()


class Api:
    def controller_set_attr(self, obj):
        (attr, value), = obj.items()
        print(f'setting {attr}={value}')

        setattr(usbl_controller, attr, value)

        ## in pywebview, return values from Python don't work reliably
        # return getattr(usbl_controller, attr)

    def get_serial_devices(self, *arg, **kwargs):
        try:
            result = [cp.device for cp in list_ports.comports()]
            result.append('/dev/debug')
            return result
        except Exception as e:
            logging.error(str(e))


window = webview.create_window('USBL Relay', url='web/main.html', js_api=Api())


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
def log_json(record): ...


@js_function
def on_controller_attr_changed(attr, value): ...


@js_function
def on_list_usb_devices(values): ...


class AppLoggingHandler(logging.Handler):
    def emit(self, record: logging.LogRecord):
        log_json({k: getattr(record, k) for k in
            ('filename', 'funcName', 'levelname', 'lineno', 'module', 'msg', 'name')})


logging.getLogger().setLevel(logging.INFO)
my_handler = AppLoggingHandler()
my_handler.setFormatter('[%(name)s] %(message)s')
logging.getLogger().addHandler(my_handler)
stream_handler = logging.StreamHandler()
stream_handler.setFormatter(logging.Formatter(
    '%(asctime)s:[%(name)s] - %(levelname)s - %(message)s'))
logging.getLogger().addHandler(stream_handler)

usbl_controller.set_change_callback(on_controller_attr_changed)

webview.start(http_server=True, debug=True)
