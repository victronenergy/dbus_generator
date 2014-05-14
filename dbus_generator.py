#!/usr/bin/python -u
# -*- coding: utf-8 -*-

# Run this with:
#	export PYTHONPATH="../velib_python"; python dbus_generator.py -d

# Function
# dbus_generator monitors the dbus for batteries (com.victronenergy.battery.*), and
# then selects the genset with battery instance 5. Later on this can be changed so
# that the used batterybank can be configured through the gui.
#
# It then monitors state of charge and current, and auto start/stops the genset based
# on the configuration settings.


from dbus.mainloop.glib import DBusGMainLoop
import gobject
import argparse
import logging
import datetime
import platform
import dbus
from os import path, pardir

# Victron imports
from dbusmonitor import DbusMonitor
from vedbus import VeDbusService
from settingsdevice import SettingsDevice


softwareversion = '0.10'
dbusgenerator = None


class DbusGenerator:
	def __init__(self):
		self._dbusservice = None
		self._batteryservice = None
		self._settings = SettingsDevice(
			bus=dbus.SystemBus() if (platform.machine() == 'armv7l') else dbus.SessionBus(),
			supportedSettings={
				'batteryinstance': ['/Settings/Generator/BatteryInstance', 0, 0, 1000],
				'autostopsoc': ['/Settings/Generator/AutoStopSOC', 90, 0, 100],
				'autostartsoc': ['/Settings/Generator/AutoStartSOC', 10, 0, 100],
				'autostartcurrent': ['/Settings/Generator/AutoStartCurrent', 0, 0, 500]
			},
			eventCallback=self._handle_changed_setting)

		# DbusMonitor expects these values to be there, even though we don need them. So just
		# add some dummy data. This can go away when DbusMonitor is more generic.
		dummy = {'code': None, 'whenToLog': 'configChange', 'accessLevel': None}

		# TODO, add monitoring the relay function, and only operate the relay/export generator to dbus
		# when the function is genset.
		self._dbusmonitor = DbusMonitor({
			'com.victronenergy.battery': {
				'/Dc/0/I': dummy,
				'/Soc': dummy},
			'com.victronenergy.settings': {
				'/Settings/Relay/Function': dummy}   # This is not our setting so do it here. not in supportedSettings
		}, self._dbus_value_changed)

		self._evaluate_if_we_are_needed()

	# Call this function on startup, when settings change or services (dis)appear
	def _evaluate_if_we_are_needed(self):
		# 0 == Alarm relay, 1 == Generator start/stop
		# Don't touch the relay when it is not ours!
		if self._dbusmonitor.get_value('com.victronenergy.settings', '/Settings/Relay/Function') == 1:

			if self._dbusservice is None:
				logging.info("Action! Going on dbus and taking control of the relay")
				self._dbusservice = VeDbusService('com.victronenergy.generator.startstop0')
				self._dbusservice.add_mandatory_paths(
					processname=__file__,
					processversion='v%s, on Python %s' % (softwareversion, platform.python_version()),
					connection='CCGX relay and Bat. instance %s' % self._settings['batteryinstance'],
					deviceinstance=0,
					productid=0,
					productname='Genset start/stop',
					firmwareversion=0,
					hardwareversion=0,
					connected=1)

				# Create our own paths
				# State: 0 = stopped, 1 = running, 2 = error: no battery to use
				self._dbusservice.add_path('/State', 2)

			# Is our battery instance available?
			batteries = self._dbusmonitor.get_service_list('com.victronenergy.battery')
			if self._settings['batteryinstance'] in batteries:
				self._batteryservice = batteries[self._settings['batteryinstance']]
			else:
				if self._batteryservice is not None:
					logging.info("Battery instance we used is of the dbus, genset will be stopped if running")

				self._batteryservice = None

			self._evaluate_startstop_conditions()

		else:

			if self._dbusservice is not None:
				# First stop the genset, so this is also signalled via the dbus
				self.stop_genset()
				self._dbusService.__del__()
				self._dbusService = None
				logging.info("Relay function is no longer genset start/stop, genset stopped and going off dbus")

	def _device_added(self, dbusservicename, instance):
		self._evaluate_if_we_are_needed()

	def _device_removed(self, dbusservicename, instance):
		self._evaluate_if_we_are_needed()

	def _dbus_value_changed(self, dbusServiceName, dbusPath, options, changes, deviceInstance):
		if dbusServiceName == self._batteryservice and deviceInstance == self._settings['batteryinstance']:
			self._evaluate_startstop_conditions()
		elif dbusServiceName == 'com.victronenergy.settings':
			self._evaluate_if_we_are_needed()

	def _handle_changed_setting(setting, oldvalue, newvalue):
		self._evaluate_startstop_conditions()

	def _our_battery_exists():
		batteries = self._dbusmonitor.get_service_list('com.victronenergy.battery')
		if self._settings['batteryinstance'] in batteries[0]:
			return batteries[1]

		return None

	def _evaluate_startstop_conditions(self):
		logging.debug("soc: %s" % (self.battery_soc()))
		if self.battery_soc() is None:
			self.stop_genset()
			return

		if self.battery_soc() <= self._settings['autostartsoc']:
			self.start_genset()

		if self.battery_soc() >= self._settings['autostopsoc']:
			self.stop_genset()

	def battery_soc(self):
		soc = self._dbusmonitor.get_value(self._batteryservice, '/Soc')
		return int(soc) if soc is not None else None

	def battery_current(self):
		current = self._dbusmonitor.get_value(self._batteryservice, '/Dc/0/I')
		return int(current) if current is not None else None

	def start_genset(self):
		logging.info("TODO: implement starting the genset")
		self._dbusservice['/State'] = 1

	def stop_genset(self):
		logging.info("TODO: implement stopping the genset")
		self._dbusservice['/State'] = 0

def main():
	# Argument parsing
	parser = argparse.ArgumentParser(
		description= 'dbus_generator auto starts/stops a genset based on battery status'
	)

	parser.add_argument("-d", "--debug", help="set logging level to debug",
					action="store_true")

	args = parser.parse_args()

	# Init logging
	logging.basicConfig(level=(logging.DEBUG if args.debug else logging.INFO))
	logging.info("%s v%s is starting up" % (__file__, softwareversion))
	logLevel = {0: 'NOTSET', 10: 'DEBUG', 20: 'INFO', 30: 'WARNING', 40: 'ERROR'}
	logging.info('Loglevel set to ' + logLevel[logging.getLogger().getEffectiveLevel()])

	# Have a mainloop, so we can send/receive asynchronous calls to and from dbus
	DBusGMainLoop(set_as_default=True)

	global dbusgenerator
	dbusgenerator = DbusGenerator()

	# Start and run the mainloop
	logging.info("Starting mainloop, responding on only events from now on")
	mainloop = gobject.MainLoop()
	mainloop.run()

if __name__ == "__main__":
	main()
