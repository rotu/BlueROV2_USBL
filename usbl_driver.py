#!/usr/bin/python
import sys
sys.path.insert(0, './pynmea2')

import pdb

import time
import pynmea2
import json
import socket
import serial
import math
from decimal import *
from os import system

# destination / output
ip="192.168.2.2"
nmeaPort = 27000
mavPort = 25100
sockitOut = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sockitOut.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
sockitOut.setblocking(False)

#Radius of Earth
R = float(6378137)

sampleRTH = "$USRTH,358.5,1.5,2.8,142.8,52.8,37.2,2.8,-0.6,1.9,178.1,271.9,16*49"
sampleGPS = "$GPGGA,200838.400,3845.0630,N,07727.2770,W,1,06,1.2,111.4,M,-33.4,M,,0000*6A"
# rthData = pynmea2.parse(sampleRTH)
# gpsData = pynmea2.parse(sampleGPS)
# rovData = pynmea2.parse(sampleGPS)

def sendToMav(newLat, newLon):
    result = {}
    result['time_usec'] = str(gpsData.timestamp)           #Timestamp (micros since boot or Unix epoch)
    result['gps_id'] = 0                #ID of the GPS for multiple GPS inputs
    result['ignore_flags'] = 1|2|4|8|16|32|64|128    #Flags indicating which fields to ignore (see GPS_INPUT_IGNORE_FLAGS enum). All other fields must be provided.
    result['time_week_ms'] = 0          #GPS time (milliseconds from start of GPS week)
    result['time_week'] = 0             #GPS week number
    result['fix_type'] = 3              #0-1: no fix, 2: 2D fix, 3: 3D fix. 4: 3D with DGPS. 5: 3D with RTK
    result['lat'] = 20*1e7                   #Latitude (WGS84), in degrees * 1E7
    result['lon'] = 30                   #Longitude (WGS84), in degrees * 1E7
    result['alt'] = 0                   #Altitude (AMSL, not WGS84), in m (positive for up)
    result['hdop'] = 1                  #GPS HDOP horizontal dilution of position in m
    result['vdop'] = 1                  #GPS VDOP vertical dilution of position in m
    result['vn'] = 0                    #GPS velocity in m/s in NORTH direction in earth-fixed NED frame
    result['ve'] = 0                    #GPS velocity in m/s in EAST direction in earth-fixed NED frame
    result['vd'] = 0                    #GPS velocity in m/s in DOWN direction in earth-fixed NED frame
    result['speed_accuracy'] = 0        #GPS speed accuracy in m/s
    result['horiz_accuracy'] = 0        #GPS horizontal accuracy in m
    result['vert_accuracy'] = 0         #GPS vertical accuracy in m
    result['satellites_visible'] = 0    #Number of satellites visible.
    result = json.dumps(result)
    print(result)
    sockitOut.sendto(result.encode(), (ip, mavPort))

def sendtoNMEARX(newLat, newLon):
    gts = str(gpsData.timestamp)
    timestamp = float(gts[0:2] + gts[3:5] + gts[6:11])
    gds = str(gpsData.datestamp)
    datestamp = str(gds[8:10] + gds[5:7] + gds[2:4])
    #pdb.set_trace()
    newMessage = pynmea2.RMC('GN', 'RMC',
        (
        str(timestamp),
        str(gpsData.status),
        str(newLat*100)[0:10],
        str(gpsData.lat_dir),
        str(newLon*100)[0:10],
        str(gpsData.lon_dir),
        str(gpsData.spd_over_grnd),
        str(""),
        str(datestamp),
        str(gpsData.mag_variation),
        str(gpsData.mag_var_dir)
        )
    )
    print("G: " , str(gpsData))
    print("N: " , str(newMessage))
    #sockitOut.sendto(b'$GNGGA,191732.20,4458.18069,N,09331.05618,W,2,12,0.80,310.1,M,-30.7,M,,0000*76', (ip, nmeaPort))

    sockitOut.sendto(str(newMessage).encode(), (ip, nmeaPort))


    #sockitOut.sendto(str(gpsData), (ip, nmeaPort))

#gpsData = pynmea2.parse("$GNGGA,191731.40,4458.18062,N,09331.05604,W,2,12,0.80,309.9,M,-30.7,M,,0000*75")
#rthData = pynmea2.parse("$USRTH,20.0,-20.0,30.0,14.8,49.3,40.7,28.3,-0.3,1.7,29.5,60.5,72*51");

while True:
    #Update Data
    try:
        with open('/dev/ttyUSB0', 'r') as dev:
            streamreader = pynmea2.NMEAStreamReader(dev)
            for msg in streamreader.next():
                rthData = msg

        with open('/dev/ttyACM0', 'r') as dev:
            streamreader = pynmea2.NMEAStreamReader(dev)
            for msg in streamreader.next():
                gpsData = msg
    except:
        print("Failed to read input")

    #Maths
    #Elevation 0 at horizon?
    #pdb.set_trace()
    hr = rthData.sr * math.cos(rthData.te)

    dn = math.cos(rthData.cb) * hr
    de = math.sin(rthData.cb) * hr

    dLat = dn / R
    #pdb.set_trace()

    dLon = de / (R * math.cos(math.pi) * gpsData.latitude / float(100))

    newLat = abs(gpsData.latitude + dLat * 180 / math.pi)
    newLon = abs(gpsData.longitude + dLon * 180 / math.pi)

    #sendToMav(newLat, newLon)
    sendtoNMEARX(newLat, newLon)
