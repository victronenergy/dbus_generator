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
	description='Multi RS system'
)

parser.add_argument("-n", "--name", help="the D-Bus service you want me to claim",
				type=str, default="com.victronenergy.acsystem.socketcan_vecan0_sys0")

args = parser.parse_args()

# Init logging
logger = setup_logging(debug=True)
logger.info(__file__ + " is starting up, use -h argument to see optional arguments")

# Have a mainloop, so we can send/receive asynchronous calls to and from dbus
DBusGMainLoop(set_as_default=True)

pvac_output = DbusDummyService(
	servicename=args.name,
	deviceinstance=0,
	productname='Multi RS system',
	paths={
		'/State': {'initial': 252, 'update': 0},
		'/Ac/ActiveIn/ActiveInput': {'initial': 0, 'update': 0},
		'/Ac/Control/IgnoreAcIn1': {'initial': 0, 'update': 0},
		'/Alarms/HighTemperature': {'initial': 0, 'update': 0},
		'/Alarms/Overload': {'initial': 0, 'update': 0},
		'/Ac/Out/P': {'initial': 80, 'update': 0},
		'/Ac/Out/L1/P': {'initial': 0, 'update': 0}}
	)

logger.info('Connected to dbus, and switching over to gobject.MainLoop() (= event based)')
mainloop = gobject.MainLoop()
mainloop.run()
