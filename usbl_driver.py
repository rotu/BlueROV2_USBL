#!/usr/bin/python3

import logging
import socket
from concurrent.futures.thread import ThreadPoolExecutor
from enum import Enum
from math import cos, radians, sin
from threading import Event
from typing import Any, Callable, Optional, Tuple

import serial
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


class Device(Enum):
    GPS = 'gps'
    USBL = 'usbl'
    ECHO = 'echo'
    MAV = 'mav'


def get_device_name_if_open(file_obj: Optional[Serial]):
    if file_obj is None:
        return None
    if not file_obj.is_open:
        return None
    return file_obj.name


executor = ThreadPoolExecutor()


class USBLController:
    _addr_echo: Optional[Tuple[str, int]] = None
    _addr_mav: Optional[Tuple[str, int]] = None

    _dev_gps: Optional[Serial] = None
    _dev_usbl: Optional[Serial] = None

    _close_gps_event: Event
    _close_usbl_event: Event

    _last_rmc: Optional[RMC] = None
    _state_change_cb: Callable[[str, Any], None]

    def set_change_callback(self, on_state_change: Callable[[str, Any], None]):
        self._state_change_cb = on_state_change

    def __init__(self, ):
        self._out_udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._out_udp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._out_udp.setblocking(False)

        self._state_change_cb = lambda key, value: None

        self._close_gps_event = Event()
        self._close_usbl_event = Event()

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
        return get_device_name_if_open(self._dev_gps)

    @dev_gps.setter
    def dev_gps(self, value):
        if self._dev_gps is not None:
            self._close_gps_event.set()
            self._dev_gps.close()
        if value is not None:
            self._close_gps_event = new_close_event = Event()
            self._dev_gps = serial.Serial(value)
            executor.submit(self._read_gps_until_close_requested, new_close_event)

    @property
    def dev_usbl(self):
        return get_device_name_if_open(self._dev_usbl)

    @dev_usbl.setter
    def dev_usbl(self, value):
        if self._dev_usbl is not None:
            self._close_usbl_event.set()
            self._dev_usbl.close()
        if value is not None:
            self._close_usbl_event = new_close_event = Event()
            self._dev_usbl = serial.Serial(value, baudrate=115200, exclusive=True,
                inter_byte_timeout=0.1)
            executor.submit(self._read_usbl_until_close_requested, new_close_event)

    def _read_gps_until_close_requested(self, close_event):
        try:
            with self._dev_gps:

                while True:
                    line = self._dev_gps.readline()
                    msg = NMEASentence.parse(line)
                    if msg.sentence_type == 'RMC':
                        self._last_rmc = msg

                    addr_echo = self._addr_echo
                    if addr_echo is not None:
                        self._out_udp.sendto(msg.encode(), addr_echo)
        except Exception as e:
            if not close_event.is_set():
                logging.error(f'GPS Reader Thread: {e}')
                self._state_change_cb('dev_gps', self.dev_gps)

    def _read_usbl_until_close_requested(self, close_event):
        try:
            with self._dev_usbl:
                while True:
                    ln = self._dev_usbl.readline()
                    rth = NMEASentence.parse(ln)
                    if rth.sentence_type != 'RTH':
                        continue

                    rmc = self._last_rmc
                    if rmc is None:
                        logging.info('ignoring RTH message because RMC is not ready yet')
                        continue

                    addr_mav = self._addr_mav
                    if addr_mav is None:
                        continue

                    new_rmc = combine_rmc_rth(rmc, rth)
                    self._out_udp.sendto(new_rmc.encode(), addr_mav)
        except Exception as e:
            if not close_event.is_set():
                logging.error(f'USBL Reader Thread: {e}')
                self._state_change_cb('dev_usbl', self.dev_usbl)
