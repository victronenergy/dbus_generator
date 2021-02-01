#!/usr/bin/python -u
# -*- coding: utf-8 -*-

from startstop import StartStop
import logging
from gen_utils import dummy, Errors

remoteprefix = 'com.victronenergy.genset'
name = "FischerPanda0"
productid = 0xB040

# List of the service/paths we need to monitor
monitoring = {
	'com.victronenergy.genset': {
		'/AutoStart': dummy,
		'/Connected': dummy,
		'/ErrorCode': dummy,
		'/ProductId': dummy,
		'/Start': dummy
		},
	'com.victronenergy.settings': {
		'/Settings/Services/FischerPandaAutoStartStop': dummy
		}
	}

# Determine if a startstop instance can be created for this device
def check_device(dbusmonitor, dbusservicename):
	# Check the product ID to determine if it's a Fischer Panda genset
	# and also check if connected.
	if remoteprefix not in dbusservicename:
		return False
	if dbusmonitor.get_value(dbusservicename, '/ProductId') != productid:
		return False
	if dbusmonitor.get_value(dbusservicename, '/Connected') != 1:
		return False
	return True

def create(dbusmonitor, dbusservice, remoteservice, settings):
	i = FischerPandaGenerator()
	i.set_sources(dbusmonitor, dbusservice, settings, name, remoteservice)
	return i

class FischerPandaGenerator(StartStop):
	def _remote_setup(self):
		# Enable if autostart is enabled for FischerPanda, later checks will be done by
		# the dbus_value_changed event.
		if self._dbusmonitor.get_value('com.victronenergy.settings',
									'/Settings/Services/FischerPandaAutoStartStop') == 1:
			self.enable()

	def _check_remote_status(self):
		error = self._dbusservice['/Error']
		autostart = bool(self._dbusmonitor.get_value(self._remoteservice, '/AutoStart'))
		# Check for genset error
		if self._dbusmonitor.get_value(self._remoteservice, '/ErrorCode') != Errors.NONE:
			self.set_error(Errors.REMOTEINFAULT)
		elif error == Errors.REMOTEINFAULT:
			self.clear_error()

		if autostart == 0 and error == Errors.NONE:
			self.set_error(Errors.REMOTEDISABLED)
		elif autostart == 1 and error == Errors.REMOTEDISABLED:
			self.clear_error()

	def _get_remote_switch_state(self):
		# Do not drive the remote switch in case of error
		# because Fischer Panda genset will clear the error when switched off
		if self.get_error() in [Errors.REMOTEDISABLED, Errors.REMOTEINFAULT]:
			return 0
		return self._dbusmonitor.get_value(self._remoteservice, '/Start')

	def dbus_value_changed(self, dbusServiceName, dbusPath, options, changes, deviceInstance):
		# Check if the user enabled or disabled the auto start/stop functionality for the Fischer Panda.
		value = None
		if dbusServiceName == 'com.victronenergy.settings':
			if dbusPath == '/Settings/Services/FischerPandaAutoStartStop':
				value = self._dbusmonitor.get_value(dbusServiceName, dbusPath)
		if value == 1:
 			self.enable()
		elif value == 0:
			self.disable()
		StartStop.dbus_value_changed(self, dbusServiceName, dbusPath, options, changes, deviceInstance)

	def _set_remote_switch_state(self, value):
		error = self._dbusservice['/Error']
		# Do not drive the remote switch in case of error
		# because the generator clears the error when switched off
		if error in [Errors.REMOTEDISABLED, Errors.REMOTEINFAULT]:
			return
		self._dbusmonitor.set_value(self._remoteservice, '/Start', value)
