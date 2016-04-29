#!/usr/bin/env python

from dbus.mainloop.glib import DBusGMainLoop
import gobject
import argparse
import sys
import os

# our own packages
sys.path.insert(1, os.path.join(os.path.dirname(__file__), '../ext/velib_python'))
from dbusdummyservice import DbusDummyService
from logger import setup_logging

# Argument parsing
parser = argparse.ArgumentParser(
	description='Multi'
)

parser.add_argument("-n", "--name", help="the D-Bus service you want me to claim",
				type=str, default="com.victronenergy.vebus.tty23")

args = parser.parse_args()

# Init logging
logger = setup_logging(debug=True)
logger.info(__file__ + " is starting up, use -h argument to see optional arguments")

# Have a mainloop, so we can send/receive asynchronous calls to and from dbus
DBusGMainLoop(set_as_default=True)

pvac_output = DbusDummyService(
	servicename=args.name,
	deviceinstance=222,
	productname='Multi',
	paths={
		'/Dc/0/Voltage': {'initial': 24, 'update': 0},
		'/Dc/0/Current': {'initial': -3, 'update': 0},
		'/Soc': {'initial': 80, 'update': 0},
		'/State': {'initial': 1, 'update': 0},
		'/Ac/ActiveIn/ActiveInput': {'initial': 0, 'update': 0},
		'/Alarms/HighTemperature': {'initial': 0, 'update': 0},
		'/Alarms/Overload': {'initial': 0, 'update': 0},
		'/Ac/Out/P': {'initial': 80, 'update': 1},
		'/Ac/Out/L1/F': {'initial': 0, 'update': 0},
		'/Ac/Out/L1/I': {'initial': 0, 'update': 0},
		'/Ac/Out/L1/P': {'initial': 0, 'update': 0},
		'/Ac/Out/L1/S': {'initial': 0, 'update': 0},
		'/Ac/Out/L1/V': {'initial': 0, 'update': 0},
		'/Ac/Out/L2/F': {'initial': 0, 'update': 0},
		'/Ac/Out/L2/I': {'initial': 0, 'update': 0},
		'/Ac/Out/L2/P': {'initial': 0, 'update': 0},
		'/Ac/Out/L2/S': {'initial': 0, 'update': 0},
		'/Ac/Out/L2/V': {'initial': 0, 'update': 0},
		'/Ac/Out/L3/F': {'initial': 0, 'update': 0},
		'/Ac/Out/L3/I': {'initial': 0, 'update': 0},
		'/Ac/Out/L3/P': {'initial': 1, 'update': 0},
		'/Ac/Out/L3/S': {'initial': 0, 'update': 0},
		'/Ac/Out/L3/V': {'initial': 0, 'update': 0},
		'/AcSensor/0/Current': {'initial': 80, 'update': 1},
		'/AcSensor/0/Energy': {'initial': 80, 'update': 1},
		'/AcSensor/0/Location': {'initial': 80, 'update': 1},
		'/AcSensor/0/Phase': {'initial': 80, 'update': 1},
		'/AcSensor/0/Power': {'initial': 80, 'update': 1},
		'/AcSensor/0/Voltage': {'initial': 80, 'update': 1},
		'/AcSensor/1/Current': {'initial': 80, 'update': 1},
		'/AcSensor/1/Energy': {'initial': 80, 'update': 1},
		'/AcSensor/1/Location': {'initial': 80, 'update': 1},
		'/AcSensor/1/Phase': {'initial': 80, 'update': 1},
		'/AcSensor/1/Power': {'initial': 80, 'update': 1},
		'/AcSensor/1/Voltage': {'initial': 80, 'update': 1},
		'/AcSensor/2/Current': {'initial': 80, 'update': 1},
		'/AcSensor/2/Energy': {'initial': 80, 'update': 1},
		'/AcSensor/2/Location': {'initial': 80, 'update': 1},
		'/AcSensor/2/Phase': {'initial': 80, 'update': 1},
		'/AcSensor/2/Power': {'initial': 80, 'update': 1},
		'/AcSensor/2/Voltage': {'initial': 80, 'update': 1},
		'/AcSensor/Count': {'initial': 3 , 'update': 0},
		'/Ac/ActiveIn/L1/P': {'initial': 0, 'update': 1},
		'/Ac/ActiveIn/L1/I': {'initial': 46, 'update':  0},
		'/Ac/ActiveIn/L1/V': {'initial': 230, 'update': 0},
		'/Ac/ActiveIn/L1/F': {'initial': 50, 'update': 0},
		'/VebusSubstate': {'initial': 0, 'update': 0},
		'/VebusMainState': {'initial': 8, 'update': 0},
		'/Ac/NumberOfPhases': {'initial': 1, 'update': 0}}
	)

logger.info('Connected to dbus, and switching over to gobject.MainLoop() (= event based)')
mainloop = gobject.MainLoop()
mainloop.run()
