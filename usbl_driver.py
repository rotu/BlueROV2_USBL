#!/usr/bin/python3

import logging
import socket
from concurrent.futures._base import Future
from concurrent.futures.thread import ThreadPoolExecutor
from enum import Enum
from math import cos, radians, sin
from threading import Event
from typing import Any, Callable, Optional, Tuple

import serial
from pynmea2 import NMEASentence, RMC, RTH, ParseError
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


executor = ThreadPoolExecutor(3)


class USBLController:
    _addr_echo: Optional[Tuple[str, int]] = None
    _addr_mav: Optional[Tuple[str, int]] = None

    _dev_gps: Optional[Serial] = None
    _dev_usbl: Optional[Serial] = None

    _gps_closing: bool
    _gps_worker: Optional[Future] = None

    _usbl_closing: bool
    _usbl_worker: Future = None

    _last_rmc: Optional[RMC] = None
    _state_change_cb: Callable[[str, Any], None]

    def set_change_callback(self, on_state_change: Callable[[str, Any], None]):
        self._state_change_cb = on_state_change

    def __init__(self):
        self._out_udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._out_udp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._out_udp.setblocking(False)

        self._state_change_cb = lambda key, value: None
        self._gps_close_event = Event()
        self._usbl_close_event = Event()

    @property
    def addr_echo(self):
        return None if self._addr_echo is None else '{}:{}'.format(*self._addr_echo)

    @addr_echo.setter
    def addr_echo(self, value):
        if not value:
            self._addr_echo = value
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
        self._gps_close_event.set()
        self._gps_close_event = Event()

        if value is not None:
            self._gps_worker = executor.submit(
                self._read_gps,
                lambda: serial.Serial(value, baudrate=4800, exclusive=True, timeout=1),
                self._gps_close_event
            )
        Future().add_done_callback(lambda:

        )

    @property
    def dev_usbl(self):
        return get_device_name_if_open(self._dev_usbl)

    @dev_usbl.setter
    def dev_usbl(self, value):
        logger = logging.getLogger('USBL')
        if self._usbl_worker is not None:
            self._usbl_closing = True
            self._dev_usbl.close()
            try:
                self._usbl_worker.result(1)
            except TimeoutError:
                logger.warning(f'Worker did not finish')

        if value is not None:
            self._usbl_closing = False
            try:
                self._dev_usbl = serial.Serial(value, baudrate=115200, exclusive=True)
                self._usbl_worker = executor.submit(self._read_usbl)
            except Exception as e:
                logger.exception(f'Failed to open device: {e}')
                raise

    def _read_gps(self, device_factory: Callable[[], Serial], close_event: Event):
        logger = logging.getLogger('GPS')
        try:
            with device_factory() as dev:
                logger.info(f'Starting to read from {dev.name}')
                while not close_event.is_set():
                    line = dev.readline()
                    addr_echo = self._addr_echo
                    if addr_echo is not None:
                        self._out_udp.sendto(line, addr_echo)
                    try:
                        msg = NMEASentence.parse(line.decode('ascii'))
                    except UnicodeDecodeError:
                        logger.warning(f'Invalid character in {line}')
                        continue
                    except ParseError as e:
                        message = e.args[0][0]
                        logger.warning(f'{message} in {line}')
                        continue
                    if msg.sentence_type == 'RMC':
                        self._last_rmc = msg
        except Exception as e:
            self._state_change_cb('dev_gps', None)
            if close_event.is_set():
                logger.info('Device closed')
            else:
                logger.error(f'Device closed unexpectedly: {e}')

    def _read_usbl(self, device_factory: Callable[[], Serial], close_event: Event):
        logger = logging.getLogger('USBL')
        try:
            with device_factory as dev:
                logger.info(f'Starting to read from {dev.name}')
                while True:
                    line = dev.readline()
                    try:
                        msg = NMEASentence.parse(line.decode('ascii'))
                    except UnicodeDecodeError:
                        logger.warning(f'Invalid character in {line}')
                        continue
                    except ParseError as e:
                        message = e.args[0][0]
                        logger.warning(f'{message} in {line}')
                        continue
                    rth = msg
                    if rth.sentence_type != 'RTH':
                        continue

                    rmc = self._last_rmc
                    if rmc is None:
                        logger.info('Ignoring message because GPS data is not ready yet')
                        continue

                    addr_mav = self._addr_mav
                    if addr_mav is None:
                        continue

                    new_rmc = combine_rmc_rth(rmc, rth)
                    self._out_udp.sendto(new_rmc.encode(), addr_mav)
        except Exception as e:
            self._state_change_cb('dev_usbl', None)
            if self._usbl_closing:
                logger.info('Device closed')
            else:
                logger.error(f'Device closed unexpectedly: {e}')
