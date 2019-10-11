#!/usr/bin/python3

import logging
import socket
from enum import Enum
from math import cos, radians, sin
from queue import Queue
from threading import Event, Thread
from typing import Any, Callable, Optional, Tuple

from pynmea2 import NMEASentence, RMC, RTH
from serial import Serial


def degrees_to_sdm(signed_degrees: float) -> (bool, int, float):
    """
    converts signed fractional degrees to triple: is_positive, int_degrees, minutes
    """
    unsigned_degrees = abs(signed_degrees)
    return (
        signed_degrees >= 0,
        int(unsigned_degrees),
        unsigned_degrees % 60
    )


def lat_long_per_meter(current_latitude_degrees):
    """Returns the number of degrees per meter, in latitude and longitude"""
    # based on https://en.wikipedia.org/wiki/Geographic_coordinate_system#Length_of_a_degree
    phi = radians(current_latitude_degrees)
    deg_lat_per_meter = 111132.92 - 559.82 * cos(2 * phi) + 1.175 * cos(4 * phi) - 0.0023 * cos(
        6 * phi)
    deg_long_per_meter = 111412.84 * cos(phi) - 93.5 * cos(3 * phi) + 0.118 * cos(5 * phi)
    return deg_lat_per_meter, deg_long_per_meter


def combine_rmc_rth(rmc: RMC, rth: RTH) -> RMC:
    compass_bearing = rth.cb
    slant_range = rth.sr
    true_elevation = rth.te

    horizontal_range = slant_range * cos(radians(true_elevation))
    d_lat, d_lon = lat_long_per_meter(rmc.latitude)
    new_lat = rmc.latitude + cos(radians(compass_bearing)) * horizontal_range * d_lat
    new_lon = rmc.latitude + sin(radians(compass_bearing)) * horizontal_range * d_lon
    lat_sgn, lat_deg, lat_min = degrees_to_sdm(new_lat)
    lon_sgn, lon_deg, lon_min = degrees_to_sdm(new_lon)
    new_rmc_data = [
        *rmc.data[:2],
        f'{lat_deg:02d}{lat_min:.5f}',
        {True: 'N', False: 'S'}[lat_sgn],
        f'{lon_deg:02d}{lon_min:.5f}',
        {True: 'E', False: 'W'}[lon_sgn],
        '',
        '',
        *rmc.data[8:]
    ]
    return RMC('GN', 'RMC', new_rmc_data)


class SerialWorkerThread:
    serial: Optional[Serial]
    q: Queue[dict]
    thread: Thread

    def done(self):
        self.q.put_nowait({'action': 'done'})
        self.thread.join()

    def set_serial_kwargs(self, serial_kwargs: Optional[dict]):
        self.q.put_nowait({'action': 'set_serial_kwargs', 'kwargs': serial_kwargs})

    def __init__(self, name: str,
        on_device_changed: Callable[[Optional[str]], None],
        on_read_line: Callable[[str], None]
    ):
        self.logger = logging.getLogger(name)
        self.thread = Thread(target=self._run, name=name + '_thread', daemon=True)
        self.q = Queue(8)
        self.on_device_changed = on_device_changed
        self.on_read_line = on_read_line

    def _run(self):
        while True:
            try:
                item = self.q.get(block=True)
                action = item['action']
                if action == 'done':
                    self.logger.info('worker shutting down')
                    return
                if action == 'set_serial_kwargs':
                    if self.serial is not None:
                        self.logger.info('closing device ' + self.serial.name)
                        self.serial.close()
                        self.serial = None
                    kwargs = action['kwargs']
                    if kwargs is not None:
                        self.serial.info('opening device ' + kwargs['port'])
                        self.serial = Serial(**kwargs)
                    self.on_device_changed(None if self.serial is None else self.serial.port)

                if self.serial is None:
                    continue
                while self.q.qsize() == 0:
                    for ln in self.serial.readlines():
                        ln_str = ln.decode('ascii', 'replace')
                        try:
                            self.on_read_line(ln_str)
                        except Exception as e:
                            self.logger.warning(str(e) + f' when processing data {ln_str}')
            finally:
                if self.serial is not None:
                    self.serial.close()
                    self.on_device_changed(None)


class USBLController:
    _addr_echo: Optional[Tuple[str, int]] = None
    _addr_mav: Optional[Tuple[str, int]] = None

    _dev_gps: Optional[str] = None
    _dev_usbl: Optional[str] = None

    _last_rmc: Optional[RMC] = None
    _state_change_cb: Callable[[str, Any], None]

    def set_change_callback(self, on_state_change: Callable[[str, Any], None]):
        self._state_change_cb = on_state_change

    def __init__(self):
        self._out_udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._out_udp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._out_udp.setblocking(False)

        self._state_change_cb = lambda key, value: None

        self._close_gps_event = Event()
        self._close_usbl_event = Event()

        self.usbl_worker = SerialWorkerThread(
            'USBL',
            on_device_changed=self._on_usbl_changed,
            on_read_line=self._on_usbl_line
        )
        self.gps_worker = SerialWorkerThread(
            'GPS',
            on_device_changed=self._on_gps_changed,
            on_read_line=self._on_gps_line
        )

    def _on_usbl_changed(self, value):
        self._dev_usbl = value
        self._state_change_cb('dev_usbl', value)

    def _on_gps_changed(self, value):
        self._dev_usbl = value
        self._state_change_cb('dev_gps', value)

    @property
    def addr_echo(self):
        return None if self._addr_echo is None else '{}:{}'.format(*self._addr_echo)

    @addr_echo.setter
    def addr_echo(self, value):
        if not value:
            self._addr_echo = None
        else:
            host, port = value.rsplit(':')
            self._addr_echo = (host, int(port))

    @property
    def addr_mav(self):
        return None if self._addr_mav is None else '{}:{}'.format(*self._addr_mav)

    @addr_mav.setter
    def addr_mav(self, value):
        if not value:
            self._addr_mav = None
        else:
            host, port = value.rsplit(':')
            self._addr_mav = (host, int(port))

    @property
    def dev_gps(self):
        return self._dev_gps

    @dev_gps.setter
    def dev_gps(self, value):
        self.gps_worker.set_serial_kwargs({'port': value, 'baudrate': 4800, 'exclusive': True})

    @property
    def dev_usbl(self):
        return self._dev_usbl

    @dev_usbl.setter
    def dev_usbl(self, value):
        self.usbl_worker.set_serial_kwargs({'port': value, 'baudrate': 115200, 'exclusive': True})

    def _on_gps_line(self, ln):
        msg = NMEASentence.parse(ln)
        if msg.sentence_type == 'RMC':
            self._last_rmc = msg

        addr_echo = self._addr_echo
        if addr_echo is not None:
            self._out_udp.sendto(msg.encode(), addr_echo)

    def _on_usbl_line(self, ln):
        rth = NMEASentence.parse(ln)
        if rth.sentence_type != 'RTH':
            return

        rmc = self._last_rmc
        if rmc is None:
            logging.info('ignoring RTH message because RMC is not ready yet')
            return

        addr_mav = self._addr_mav
        if addr_mav is None:
            return

        new_rmc = combine_rmc_rth(rmc, rth)
        self._out_udp.sendto(new_rmc.encode(), addr_mav)
