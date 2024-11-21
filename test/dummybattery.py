#!/usr/bin/env python

from dbus.mainloop.glib import DBusGMainLoop
from gi.repository import GLib
import argparse
import sys
import os

# our own packages
sys.path.insert(1, os.path.join(os.path.dirname(__file__), '../ext/velib_python'))
from dbusdummyservice import DbusDummyService
from logger import setup_logging

# Argument parsing
parser = argparse.ArgumentParser(
	description='dummy dbus service'
)

parser.add_argument("-n", "--name", help="the D-Bus service you want me to claim",
				type=str, default="com.victronenergy.battery.tty22")

args = parser.parse_args()

# Init logging
logger = setup_logging(debug=True)
logger.info(__file__ + " is starting up, use -h argument to see optional arguments")

# Have a mainloop, so we can send/receive asynchronous calls to and from dbus
DBusGMainLoop(set_as_default=True)

pvac_output = DbusDummyService(
	servicename=args.name,
	productname='Battery',
	deviceinstance=223,
	paths={
		'/Dc/0/Voltage': {'initial': 2, 'update': 0},
		'/Dc/0/Current': {'initial': -15, 'update': 0},
		'/Soc': {'initial': 10, 'update': 0}})

print('Connected to dbus, and switching over to GLib.MainLoop() (= event based)')
mainloop = GLib.MainLoop()
mainloop.run()
