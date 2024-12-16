#!/usr/bin/env python

from dbus.mainloop.glib import DBusGMainLoop
from gi.repository import GObject as gobject
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
		'/State': {'initial': 4, 'update': 0},
		'/Ac/NumberOfPhases': {'initial': 1, 'update': 0},
		'/Mode': {'initial': 3, 'update': 0},
		'/Ac/ActiveIn/ActiveInput': {'initial': 0, 'update': 0},
		'/VebusError': {'initial': 0},
		'/Alarms/TemperatureSensor': {'initial': 0},
		'/Alarms/VoltageSensor': {'initial': 0},
		'/Alarms/LowBattery': {'initial': 0},
		'/Alarms/Ripple': {'initial': 0},
		'/Alarms/PhaseRotation': {'initial': 0},
		'/Alarms/L1/HighTemperature': {'initial': 0},
		'/Alarms/L1/Overload': {'initial': 0},
		'/Alarms/GridLost': {'initial': 0},
		'/Alarms/HighDcVoltage': {'initial': 0},
		'/Alarms/HighDcCurrent': {'initial': 0},
		'/Ac/Out/P': {'initial': 80, 'update': 0},
		'/Ac/Out/L1/I': {'initial': 0, 'update': 0},
		'/Ac/Out/L1/P': {'initial': 0, 'update': 0}}
	)

logger.info('Connected to dbus, and switching over to gobject.MainLoop() (= event based)')
mainloop = gobject.MainLoop()
mainloop.run()
