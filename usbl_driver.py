#!/usr/bin/python
import sys
sys.path.insert(0, './pynmea2')

import time
import pynmea2
import json
import socket
import serial
from os import system

# destination / output
ip="192.168.2.2"
portnum = 27000
sockitOut = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
# sockitOut.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
# sockitOut.setblocking(False)

#Radius of Earth
R = 6378137

# gpsData = {
#     'time_usec' : 0,                        # (uint64_t) Timestamp (micros since boot or Unix epoch)
#     'gps_id' : 0,                           # (uint8_t) ID of the GPS for multiple GPS inputs
#     'ignore_flags' : 56,                    # (uint16_t) Flags indicating which fields to ignore (see GPS_INPUT_IGNORE_FLAGS enum). All other fields must be provided.
#     'time_week_ms' : 0,                     # (uint32_t) GPS time (milliseconds from start of GPS week)
#     'time_week' : 0,                        # (uint16_t) GPS week number
#     'fix_type' : 3,                         # (uint8_t) 0-1: no fix, 2: 2D fix, 3: 3D fix. 4: 3D with DGPS. 5: 3D with RTK
#     'lat' : 0,                              # (int32_t) Latitude (WGS84), in degrees * 1E7
#     'lon' : 0,                              # (int32_t) Longitude (WGS84), in degrees * 1E7
#     'alt' : 0,                              # (float) Altitude (AMSL, not WGS84), in m (positive for up)
#     'hdop' : 0,                             # (float) GPS HDOP horizontal dilution of position in m
#     'vdop' : 0,                             # (float) GPS VDOP vertical dilution of position in m
#     'vn' : 0,                               # (float) GPS velocity in m/s in NORTH direction in earth-fixed NED frame
#     've' : 0,                               # (float) GPS velocity in m/s in EAST direction in earth-fixed NED frame
#     'vd' : 0,                               # (float) GPS velocity in m/s in DOWN direction in earth-fixed NED frame
#     'speed_accuracy' : 0,                   # (float) GPS speed accuracy in m/s
#     'horiz_accuracy' : 0,                   # (float) GPS horizontal accuracy in m
#     'vert_accuracy' : 0,                    # (float) GPS vertical accuracy in m
#     'satellites_visible' : 0                # (uint8_t) Number of satellites visible.
# }
#
# rthData = {
#     'ab' : 0,
#     'ac' : 0,
#     'ae' : 0,
#     'sr' : 0,
#     'tb' : 0,
#     'cb' : 0,
#     'te' : 0,
#     'er' : 0,
#     'ep' : 0,
#     'ey' : 0,
#     'ch' : 0,
#     'db' : 0
# }
#
# rovData = {
#     'time_usec' : 0,                        # (uint64_t) Timestamp (micros since boot or Unix epoch)
#     'gps_id' : 0,                           # (uint8_t) ID of the GPS for multiple GPS inputs
#     'ignore_flags' : 56,                    # (uint16_t) Flags indicating which fields to ignore (see GPS_INPUT_IGNORE_FLAGS enum). All other fields must be provided.
#     'time_week_ms' : 0,                     # (uint32_t) GPS time (milliseconds from start of GPS week)
#     'time_week' : 0,                        # (uint16_t) GPS week number
#     'fix_type' : 3,                         # (uint8_t) 0-1: no fix, 2: 2D fix, 3: 3D fix. 4: 3D with DGPS. 5: 3D with RTK
#     'lat' : 0,                              # (int32_t) Latitude (WGS84), in degrees * 1E7
#     'lon' : 0,                              # (int32_t) Longitude (WGS84), in degrees * 1E7
#     'alt' : 0,                              # (float) Altitude (AMSL, not WGS84), in m (positive for up)
#     'hdop' : 0,                             # (float) GPS HDOP horizontal dilution of position in m
#     'vdop' : 0,                             # (float) GPS VDOP vertical dilution of position in m
#     'vn' : 0,                               # (float) GPS velocity in m/s in NORTH direction in earth-fixed NED frame
#     've' : 0,                               # (float) GPS velocity in m/s in EAST direction in earth-fixed NED frame
#     'vd' : 0,                               # (float) GPS velocity in m/s in DOWN direction in earth-fixed NED frame
#     'speed_accuracy' : 0,                   # (float) GPS speed accuracy in m/s
#     'horiz_accuracy' : 0,                   # (float) GPS horizontal accuracy in m
#     'vert_accuracy' : 0,                    # (float) GPS vertical accuracy in m
#     'satellites_visible' : 0                # (uint8_t) Number of satellites visible.
# }

while True:
    #Update Data
    with open('/dev/ttyUSB0', 'r') as dev:
        streamreader = pynmea2.NMEAStreamReader(dev)
        for msg in streamreader.next():
            rthData = msg

    with open('/dev/ttyACM0', 'r') as dev:
        streamreader = pynmea2.NMEAStreamReader(dev)
        for msg in streamreader.next():
            gpsData = msg
            rovData = msg

    #Maths
    #Elevation 0 at horizon?
    hr = rthData.sr * Math.cos(rthData.te)

    dn = math.cos(rthData.cb) * hr
    de = math.sin(rthData.cb) * hr

    dLat = dn / R
    dLon = de / (R * math.cos(math.pi * lat / 100))

    newLat = lat + dlat * 180 / math.pi
    newLon  lon + dLon * 180 / math.pi

    rovData.lat = newLat
    rovData.lon = newLon

    #Send ROV data
    print(rovData)
    sockitOut.sendto(str(rovData), (ip, portnum))
