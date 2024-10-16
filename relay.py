#!/usr/bin/python -u
# -*- coding: utf-8 -*-

from startstop import StartStop
import logging
import dbus
import monotonic_time
from gen_utils import States, dummy

remoteprefix = 'com.victronenergy.system'
name = "Generator0"
device_instance = 0

# List of the service/paths we need to monitor
monitoring = {
	'com.victronenergy.settings': {
		'/Settings/Relay/Function': dummy,
		'/Settings/Relay/Polarity': dummy,
		},
	'com.victronenergy.system': {
		'/Relay/0/State': dummy,
		'/DeviceInstance': dummy,
		}
	}

# Determine if a startstop instance can be created for this device
def check_device(dbusmonitor, service):
	# Built-in relay has not its own service so this check must always
	# return false.
	return False

def create(dbusmonitor, remoteservice, settings):
	i = RelayGenerator(device_instance)
	i.set_sources(dbusmonitor, settings, name, remoteservice)
	return i

class RelayGenerator(StartStop):
	_driver = 0 # Relay
	_digitalInput = 0

	def _remote_setup(self):
		self.enable()
		# Make sure that the relay polarity is set to normally open.
		if self._dbusmonitor.get_value('com.victronenergy.settings', '/Settings/Relay/Polarity') == 1:
			self._dbusmonitor.set_value('com.victronenergy.settings', '/Settings/Relay/Polarity', 0)

	def _running_by_digital_input(self, path, value):
		if path == '/DigitalInput/Running':
			if value == 1: # Running
				super()._generator_started()
			else: # Stopped
				super()._generator_stopped()

		elif path == '/DigitalInput/Input':
			self._digitalInput = value
			if value == 0:
				# No longer using the digital input to update runtime. Sync running with the state of startstop.
				if (not self._generator_running and self._dbusservice['/State'] in (States.RUNNING, States.WARMUP, States.COOLDOWN, States.STOPPING)):
					super()._generator_started() # Digital input was "Stopped", but control service is running -> Start counting runtime.
				elif (self._generator_running and self._dbusservice['/State'] not in (States.RUNNING, States.WARMUP, States.COOLDOWN, States.STOPPING)):
					super()._generator_stopped() # Digital input was "Running" but control service is stopped -> Stop counting runtime.
				logging.info('No longer using digital input to count runtime for startstop instance %d' % device_instance)
			else:
				logging.info('Using digital input %d to count runtime for startstop instance %d' % (value, device_instance))
				# Sync runtime counting with the state of the digital input.
				if self._dbusservice['/DigitalInput/Running'] == 1:
					super()._generator_started()
				else:
					super()._generator_stopped()

		return True

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
		self._dbusmonitor.set_value_async(self._remoteservice, '/Relay/0/State', value)

		# No digital input to monitor the generator, assume that it runs based on the state of the relay
		if self._digitalInput == 0:
			super()._generator_started() if value else super()._generator_stopped()