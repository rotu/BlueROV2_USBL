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

#Samples
#sampleRTH = "$USRTH,358.5,1.5,2.8,142.8,52.8,37.2,2.8,-0.6,1.9,178.1,271.9,16*49"
#sampleGPS = "$GPGGA,200838.400,3845.0630,N,07727.2770,W,1,06,1.2,111.4,M,-33.4,M,,0000*6A"
# rthData = pynmea2.parse(sampleRTH)
# gpsData = pynmea2.parse(sampleGPS)
# rovData = pynmea2.parse(sampleGPS)

def sendtoNMEARX(newLatString, newLonString):
    gts = str(gpsData.timestamp)
    timestamp = float(gts[0:2] + gts[3:5] + gts[6:11])
    gds = str(gpsData.datestamp)
    datestamp = str(gds[8:10] + gds[5:7] + gds[2:4])
    #pdb.set_trace()

    latString = newLat
    newMessage = pynmea2.RMC('GN', 'RMC',
        (
        str(timestamp),
        str(gpsData.status),
        str(newLatString),
        str(gpsData.lat_dir),
        str(newLonString),
        str(gpsData.lon_dir),
        str(gpsData.spd_over_grnd),
        str(""),
        str(datestamp),
        str(gpsData.mag_variation),
        str(gpsData.mag_var_dir),
        )
    )

    sendingMessage = gpsData
    #sendingMessage = newMessage

    print("RTH: " , str(rthData))
    print("GPS: " , str(gpsData))
    print("NEW: " , str(sendingMessage))
    print("-----------------------------------------------------")

    #Tests with data that actually works over socat
    #sockitOut.sendto(b'$GNGGA,191732.20,4458.18069,N,09331.05618,W,2,12,0.80,310.1,M,-30.7,M,,0000*76', (ip, nmeaPort))
    #sockitOut.sendto('$GNGGA,203637.00,4458.17333,N,09331.05019,W,1,07,1.74,298.5,M,-30.7,M,,*74', (ip, nmeaPort))

    #pdb.set_trace()
    sockitOut.sendto(str(sendingMessage), (ip, nmeaPort))

def ddToDDM(dd):
    is_positive = dd >= 0
    dd = abs(dd)
    degrees,minutes = divmod(dd*60,60)
    degrees = degrees if is_positive else -degrees
    return (degrees,minutes)

while True:
    #Update Data
    gotData = False
    try:
        with open('/dev/ttyUSB0', 'r') as dev:
            streamreader = pynmea2.NMEAStreamReader(dev)
            for msg in streamreader.next():
                rthData = msg

        with open('/dev/ttyACM0', 'r') as dev:
            streamreader = pynmea2.NMEAStreamReader(dev)
            for msg in streamreader.next():
                gpsData = msg

        gotData = True
    except:

        print("Failed to read input")
    if gotData:

        #Maths
        #compassBearing = (rthData.cb)
        #slantRange = rthData.sr
        #trueElevation = rthData.te


        #Fake the RTH Data for now
        compassBearing = 90
        slantRange = 1000
        trueElevation =-5

        horizontalRange = slantRange * math.cos(math.radians(trueElevation))

        dn = math.sin(math.radians(compassBearing)) * horizontalRange
        de = math.cos(math.radians(compassBearing)) * horizontalRange

        dLat = dn / R
        dLon = de / (R * math.cos(math.pi) * gpsData.latitude / float(100))

        newLat = abs(gpsData.latitude + dLat * 180 / math.pi)
        newLon = abs(gpsData.longitude + dLon * 180 / math.pi)

        newLatDegrees, newLatMinutes = ddToDDM(newLat)
        newLonDegrees, newLonMinutes = ddToDDM(newLon)

        newLatString = format(newLatDegrees, '.0f') + format(newLatMinutes, '.5f')
        newLonString = format(newLonDegrees, '.0f') + format(newLonMinutes, '.5f')
        #pdb.set_trace()

        sendtoNMEARX(newLatString, newLonString)
