#!/usr/bin/python3
import socket
import time
from math import cos, radians, sin
from threading import Thread

import pynmea2

gps_stream = open('/dev/ttyACM0', 'rb')
usbl_stream = open('/dev/ttyUSB0', 'rb')

# destination / output
ip = "192.168.2.2"
nmea_port = 27000
mav_port = 25100


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


def main():
    rmc = None
    out_udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    out_udp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    out_udp.setblocking(False)

    def get_latest_rmc():
        nonlocal rmc
        with gps_stream:
            while True:
                for msg in pynmea2.NMEAStreamReader(gps_stream):
                    if msg.sentence_type == 'RMC':
                        rmc = msg

    gps_thread = Thread(target=get_latest_rmc)
    gps_thread.start()

    while rmc is None:
        print('waiting for initial GPS data...')
        time.sleep(1)

    with usbl_stream:
        for rth in pynmea2.NMEAStreamReader(usbl_stream):
            assert isinstance(rth, pynmea2.RTH)
            assert isinstance(rmc, pynmea2.RMC)

            new_rmc = combine_rmc_rth(rmc, rth)
            out_udp.sendto(new_rmc.encode(), (ip, nmea_port))
