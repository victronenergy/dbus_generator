#!/usr/bin/python -u
# -*- coding: utf-8 -*-

from startstop import StartStop
import logging
import dbus
from gen_utils import dummy

remoteprefix = 'com.victronenergy.system'
name = "Generator0"
# List of the service/paths we need to monitor
monitoring = {
	'com.victronenergy.settings': {
		'/Settings/Relay/Function': dummy,
		'/Settings/Relay/Polarity': dummy,
		},
	'com.victronenergy.system': {
		'/Relay/0/State': dummy
		}
	}

# Determine if a startstop instance can be created for this device
def check_device(dbusmonitor, dbuspath):
	# Built-in relay has not its own service so this check must always
	# return false.
	return False

def create(dbusmonitor, dbusservice, remoteservice, settings):
	i = RelayGenerator()
	i.set_sources(dbusmonitor, dbusservice, settings, name, remoteservice)
	return i

class RelayGenerator(StartStop):

	def _remote_setup(self):
		self.enable()
		# Make sure that the relay polarity is set to normally open.
		polarity = self._dbusmonitor.get_item('com.victronenergy.settings', '/Settings/Relay/Polarity')
		if polarity.get_value() == 1:
			polarity.set_value(dbus.Int32(0, variant_level=1))

	def remove(self):
		# Open the relay before stop controlling it
		self._set_remote_switch_state(0)
		StartStop.remove(self)

	def _check_remote_status(self):
		# Nothing to check
		pass

	def _get_remote_switch_state(self):
		return self._dbusmonitor.get_value(self._remoteservice, '/Relay/0/State')

	def _set_remote_switch_state(self, value):
		self._dbusmonitor.get_item(self._remoteservice, '/Relay/0/State').set_value(value)
