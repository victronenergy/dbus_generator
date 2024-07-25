#!/usr/bin/python -u
# -*- coding: utf-8 -*-

from startstop import StartStop
import logging
from gen_utils import dummy, Errors

remoteprefix = r'com.victronenergy.(dc)?genset'
name = "Generator1"
device_instance = 1

# List of the service/paths we need to monitor
monitoring = {
	'com.victronenergy.genset': {
		'/RemoteStartModeEnabled': dummy,
		'/Connected': dummy,
		'/Error/0/Id': dummy,
		'/ProductId': dummy,
		'/DeviceInstance': dummy,
		'/Start': dummy
		},
	'com.victronenergy.dcgenset': {
		'/RemoteStartModeEnabled': dummy,
		'/Connected': dummy,
		'/Error/0/Id': dummy,
		'/ProductId': dummy,
		'/DeviceInstance': dummy,
		'/Start': dummy
		}
	}

# Determine if a startstop instance can be created for this device
def check_device(dbusmonitor, dbusservicename):
	# Check if genset service supports remote start and is connected.
	if not dbusmonitor.seen(dbusservicename, '/RemoteStartModeEnabled'):
		return False
	if dbusmonitor.get_value(dbusservicename, '/Connected') != 1:
		return False
	return True

def create(dbusmonitor, remoteservice, settings):
	i = Genset(device_instance)
	i.set_sources(dbusmonitor, settings, name, remoteservice)
	return i

class Genset(StartStop):
	_driver = 1 # Genset service
	def _remote_setup(self):
		self.enable()

	def _check_remote_status(self):
		error = self._dbusservice['/Error']
		remotestart = bool(self._dbusmonitor.get_value(self._remoteservice, '/RemoteStartModeEnabled'))
		# Check for genset error, also accept absence of the error path as valid no-error condition
		if self._dbusmonitor.get_value(self._remoteservice, '/Error/0/Id'):
			self.set_error(Errors.REMOTEINFAULT)
		elif error == Errors.REMOTEINFAULT:
			self.clear_error()

		if remotestart == 0 and error == Errors.NONE:
			self.set_error(Errors.REMOTEDISABLED)
		elif remotestart == 1 and error == Errors.REMOTEDISABLED:
			self.clear_error()

	def _get_remote_switch_state(self):
		# Do not drive the remote switch in case of error
		# because Fischer Panda genset will clear the error when switched off
		if self.get_error() in [Errors.REMOTEDISABLED, Errors.REMOTEINFAULT]:
			return 0
		return self._dbusmonitor.get_value(self._remoteservice, '/Start')

	def _set_remote_switch_state(self, value):
		error = self._dbusservice['/Error']
		# Do not drive the remote switch in case of error
		# because the generator clears the error when switched off
		if error in [Errors.REMOTEDISABLED, Errors.REMOTEINFAULT]:
			return
		self._dbusmonitor.set_value_async(self._remoteservice, '/Start', value)
