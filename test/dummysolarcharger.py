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
                type=str, default="com.victronenergy.solarcharger.tty33")

args = parser.parse_args()

logger = setup_logging(debug=True)
logger.info(__file__ + " is starting up, use -h argument to see optional arguments")

# Have a mainloop, so we can send/receive asynchronous calls to and from dbus
DBusGMainLoop(set_as_default=True)

s = DbusDummyService(
    servicename=args.name,
    deviceinstance=0,
    paths={
        '/Dc/0/Voltage': {'initial': 12},
        '/Dc/0/Current': {'initial': 0},
	    '/Dc/0/Power': {'initial': 290, 'update': 1}
},
    productname='Solarcharger',
    connection='VE.Direct port 1')

logger.info('Connected to dbus, and switching over to GLib.MainLoop() (= event based)')
mainloop = GLib.MainLoop()
mainloop.run()

