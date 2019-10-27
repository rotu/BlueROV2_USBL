#!/usr/bin/python3
import logging
import socket
import traceback
from io import RawIOBase
from math import cos, radians, sin, degrees
from pathlib import Path
from queue import Queue
from threading import Event, Thread
from typing import Any, Callable, Optional, Tuple

from pynmea2 import ChecksumError, NMEASentence, ParseError, RMC, RTH, SentenceTypeError
from serial import Serial
from serial.tools import list_ports

from bluerov2_usbl.mock_serial import MockSerial


def degrees_to_sdm(signed_degrees: float) -> (bool, int, float):
    """
    converts signed fractional degrees to triple: is_positive, int_degrees, minutes
    """
    unsigned_degrees = abs(signed_degrees)
    return (
        signed_degrees >= 0,
        int(unsigned_degrees),
        (unsigned_degrees * 60) % 60
    )


#
# def lat_lon_per_meter(current_latitude_degrees):
#     """Returns the number of degrees per meter, in latitude and longitude"""
#     # # based on https://en.wikipedia.org/wiki/Geographic_coordinate_system#Length_of_a_degree
#     # phi = radians(current_latitude_degrees)
#     # meters_per_lat = 111132.92 - 559.82 * cos(2 * phi) + 1.175 * cos(4 * phi) - 0.0023 * cos(
#     #     6 * phi)
#     # meters_per_lon = 111412.84 * cos(phi) - 93.5 * cos(3 * phi) + 0.118 * cos(5 * phi)
#
#     #https://gis.stackexchange.com/questions/2951/algorithm-for-offsetting-a-latitude
#     -longitude-by-some-amount-of-meters/2968
#     R = 6378137
#     lat_per_meter = degrees(1/R)
#     lon_per_meter = degrees(1/(R*cos(radians(current_latitude_degrees))))
#
#     return lat_per_meter, lon_per_meter
#

def combine_rmc_rth(rmc: RMC, rth: RTH) -> RMC:
    compass_bearing = rth.cb
    slant_range = rth.sr
    true_elevation = rth.te

    horizontal_range = slant_range * cos(radians(true_elevation))

    dn = cos(radians(compass_bearing)) * horizontal_range
    de = sin(radians(compass_bearing)) * horizontal_range
    R = 6378137

    dLat = dn / R
    dLon = de / (R * cos(radians(rmc.latitude)))

    new_lat = rmc.latitude + degrees(dLat)
    new_lon = rmc.longitude + degrees(dLon)

    # newLatDegrees, newLatMinutes = ddToDDM(newLat)
    # newLonDegrees, newLonMinutes = ddToDDM(newLon)

    # d_lat, d_lon = lat_lon_per_meteddr(rmc.latitude)
    # new_lat = rmc.latitude + cos(radians(compass_bearing)) * horizontal_range * d_lat
    # new_lon = rmc.longitude + sin(radians(compass_bearing)) * horizontal_range * d_lon
    lat_sgn, lat_deg, lat_min = degrees_to_sdm(new_lat)
    lon_sgn, lon_deg, lon_min = degrees_to_sdm(new_lon)
    new_rmc_data = [
        *rmc.data[:2],
        f'{lat_deg:02d}{lat_min:06.3f}',
        {True: 'N', False: 'S'}[lat_sgn],
        f'{lon_deg:02d}{lon_min:06.3f}',
        {True: 'E', False: 'W'}[lon_sgn],
        '',
        '',
        *rmc.data[8:]
    ]
    return RMC('GN', 'RMC', new_rmc_data)


class SerialWorkerThread:
    serial: Optional[RawIOBase] = None
    action_queue: Queue  # [dict]
    thread: Thread

    def done(self):
        """Terminate the thread"""
        self.action_queue.put_nowait({'action': 'done'})
        self.thread.join()

    def set_serial_kwargs(self, serial_kwargs: Optional[dict]):
        self.action_queue.put_nowait({'action': 'set_serial_kwargs', 'kwargs': serial_kwargs})

    def __init__(
        self, thread_name: str,
        on_device_changed: Callable[[Optional[str]], None],
        on_read_line: Callable[[str], None],
    ):
        self.action_queue = Queue(2)
        self.on_device_changed = on_device_changed
        self.on_read_line = on_read_line
        self.thread = Thread(target=self._run, name=thread_name, daemon=True)
        self.thread.start()

    def _run(self):
        while True:
            try:
                item = self.action_queue.get(block=True)
                action = item['action']
                if action == 'done':
                    logging.info('worker shutting down')
                    return
                if action == 'set_serial_kwargs':
                    if self.serial is not None:
                        logging.info('closing device ' + self.serial.name)
                        self.serial.close()
                        self.serial = None
                    kwargs = item['kwargs']
                    if kwargs is not None:
                        port = kwargs['port']
                        logging.info(f'opening device {port}')
                        if Path(port).is_file():
                            logging.info(
                                '(This is a file, not a serial port. Only use this feature for '
                                'debugging purposes)')
                            self.serial = MockSerial(**kwargs)
                        else:
                            self.serial = Serial(**kwargs)
                    self.on_device_changed(None if self.serial is None else self.serial.name)

                if self.serial is None:
                    continue
                while self.action_queue.qsize() == 0:
                    ln = self.serial.readline()
                    if not ln.strip():
                        continue
                    ln_str = ln.decode('ascii', 'replace')
                    try:
                        self.on_read_line(ln_str)
                    except Exception as e:
                        logging.warning(f'when processing data {ln}: {traceback.format_exc()}')
            except Exception:
                logging.error(f'Device encountered an error: {traceback.format_exc()}')
            finally:
                if self.serial is not None:
                    self.serial.close()
                    self.on_device_changed(None)
                logging.info(f'Closed device')


def list_serial_ports():
    return list(list_ports.comports())


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
            thread_name='usbl',
            on_device_changed=self._on_usbl_changed,
            on_read_line=self._on_usbl_line,
        )
        self.gps_worker = SerialWorkerThread(
            thread_name='gps',
            on_device_changed=self._on_gps_changed,
            on_read_line=self._on_gps_line,
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

        self.gps_worker.set_serial_kwargs(
            None if value is None else {'port': value, 'baudrate': 4800,
                'timeout': 0.3})

    @property
    def dev_usbl(self):
        return self._dev_usbl

    @dev_usbl.setter
    def dev_usbl(self, value):

        self.usbl_worker.set_serial_kwargs(None if value is None else {
            'port': value, 'baudrate': 115200, 'timeout': 0.3})

    def _on_gps_line(self, ln):
        addr_echo = self._addr_echo
        if addr_echo is not None:
            self._out_udp.sendto(ln.encode(), addr_echo)

        if ln[3:6] != 'RMC':
            return
        try:
            rmc = NMEASentence.parse(ln)
        except ChecksumError:
            logging.debug(f'Ignoring message with bad checksum: {ln}')
            return
        except SentenceTypeError:
            logging.debug(f'Ignoring message with unrecognized sentence type: {ln}')
            return
        except ParseError:
            return
        # logging.info(ln)
        if not rmc.is_valid:
            logging.info(f'No GPS fix.')
            return

        self._last_rmc = rmc

    def _on_usbl_line(self, ln):
        rth = NMEASentence.parse(ln)
        logging.info('RTH: ' + ln)
        if rth.sentence_type != 'RTH':
            logging.debug(f'Ignoring unexpected message from USBL. Expected a RTH sentence: {rth}')
            return

        rmc = self._last_rmc
        if rmc is None:
            logging.info('ignoring RTH message because RMC is not ready yet')
            return

        addr_mav = self._addr_mav
        if addr_mav is None:
            return

        new_rmc = combine_rmc_rth(rmc, rth)
        self._out_udp.sendto(str(new_rmc).encode('ascii') + b'\r\n', addr_mav)
