#!/usr/bin/python3
import socket
from math import cos, radians, sin
from threading import Thread
from typing import Optional, Tuple

import pynmea2


#
# gps_stream = open('/dev/ttyACM0', 'rb')
# usbl_stream = open('/dev/ttyUSB0', 'rb')
#
# # destination / output
# ip = "192.168.2.2"
# nmea_port = 27000
# mav_port = 25100


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


def combine_rmc_rth(rmc: pynmea2.RMC, rth: pynmea2.RTH) -> pynmea2.RMC:
    compass_bearing = rth.cb
    slant_range = rth.sr
    true_elevation = rth.te

    # Fake the RTH Data for now
    # compassBearing = 270
    # slantRange = 100
    # trueElevation =-10

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
    return pynmea2.RMC('GN', 'RMC', new_rmc_data)


# def main():
#     rmc = None
#     out_udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
#     out_udp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
#     out_udp.setblocking(False)
#
#     def get_latest_rmc():
#         nonlocal rmc
#         with gps_stream:
#             while True:
#                 for msg in pynmea2.NMEAStreamReader(gps_stream):
#                     if msg.sentence_type == 'RMC':
#                         rmc = msg
#
#     gps_thread = Thread(target=get_latest_rmc)
#     gps_thread.start()
#
#     while rmc is None:
#         print('waiting for initial GPS data...')
#         time.sleep(1)
#
#     with usbl_stream:
#         for rth in pynmea2.NMEAStreamReader(usbl_stream):
#             assert isinstance(rth, pynmea2.RTH)
#             assert isinstance(rmc, pynmea2.RMC)
#
#             new_rmc = combine_rmc_rth(rmc, rth)
#             out_udp.sendto(new_rmc.encode(), (ip, nmea_port))


class USBLController:
    run_gps_thread: bool = False
    thread_gps: Optional[Thread] = None
    run_usbl_thread: bool = False
    thread_usbl: Optional[Thread] = None

    udp_dest_echo_rmc: Optional[Tuple[str, int]]
    udp_dest_rov_rmc: Optional[Tuple[str, int]]

    last_rmc = None

    def __init__(self):
        udp_send_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp_send_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        udp_send_socket.setblocking(False)
        self.udp_send_socket = udp_send_socket

    def _gps_thread_target(self, dev_gps):
        with dev_gps:
            while self.run_gps_thread:
                for rmc in pynmea2.NMEAStreamReader(dev_gps):
                    if rmc.sentence_type == 'RMC':
                        self.last_rmc = rmc
                    if self.udp_dest_echo_rmc:
                        self.udp_send_socket.sendto(rmc.encode(), self.udp_dest_echo_rmc)

    def set_dev_gps(self, path):
        if self.thread_gps:
            self.run_gps_thread = False
            self.thread_gps.join()

        if path is None:
            return

        self.run_gps_thread = True
        self.thread_gps = Thread(target=self._gps_thread_target, args=[open(path, 'rb')])
        self.thread_gps.start()

    def _usbl_thread_target(self, dev_usbl):
        while self.run_usbl_thread:
            with dev_usbl:
                for rth in pynmea2.NMEAStreamReader(dev_usbl):
                    if rth.sentence_type != 'RTH':
                        continue
                    assert isinstance(rth, pynmea2.RTH)
                    if self.last_rmc is None:
                        continue
                    rov_rmc = combine_rmc_rth(self.last_rmc, rth)
                    if self.udp_dest_rov_rmc is None:
                        continue
                    self.udp_send_socket.sendto(rov_rmc, self.udp_dest_rov_rmc)

    def set_dev_usbl(self, path):
        if self.thread_usbl:
            self.run_usbl_thread = False
            self.thread_usbl.join()

        if path is None:
            return

        self.run_usbl_thread = True
        self.thread_usbl = Thread(target=self._usbl_thread_target, args=[open(path, 'rb')])
        self.thread_usbl.start()
