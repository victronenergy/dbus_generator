#!/usr/bin/python -u
# -*- coding: utf-8 -*-

from startstop import StartStop
import logging
import monotonic_time
from gen_utils import dummy, Errors, States

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
		'/Start': dummy,
		'/Engine/OperatingHours': dummy,
		'/StatusCode': dummy
		},
	'com.victronenergy.dcgenset': {
		'/Dc/0/Current': dummy,
		'/RemoteStartModeEnabled': dummy,
		'/Connected': dummy,
		'/Error/0/Id': dummy,
		'/ProductId': dummy,
		'/DeviceInstance': dummy,
		'/Start': dummy,
		'/Engine/OperatingHours': dummy,
		'/StatusCode': dummy
		},
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
def check_device(dbusmonitor, dbusservicename):
	# Check if genset service supports remote start and is connected.
	if not dbusmonitor.seen(dbusservicename, '/RemoteStartModeEnabled'):
		return False
	if dbusmonitor.get_value(dbusservicename, '/Connected') != 1:
		return False
	return True

def create(dbusmonitor, remoteservice, settings):
	if remoteservice.split('.')[2] == 'dcgenset':
		i = DcGenset(device_instance)
		settings.addSettings({'nogeneratoratdcinalarm{}'.format(name): ['/Settings/{}/Alarms/NoGeneratorAtDcIn'.format(name), 0, 0, 1]})
	else:
		i = Genset(device_instance)

	i.set_sources(dbusmonitor, settings, name, remoteservice)
	return i

class Genset(StartStop):
	_driver = 1 # Genset service
	_helperrelayservice = None
	_count_runtime_with_genset = False

	def _remote_setup(self):
		self.enable()
		self._check_enable_conditions(self._dbusmonitor.get_value('com.victronenergy.settings', '/Settings/Relay/Function'))
		status_code = self._dbusmonitor.get_value(self._remoteservice, '/StatusCode')
		self._count_runtime_with_genset = status_code is not None
		if self._count_runtime_with_genset:
			self._check_if_running(status_code)

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

	def _check_enable_conditions(self, relaysetting):
		# If there's a helper relay, the start/stop service is enabled.
		if (relaysetting == 5):
			self._helperrelayservice = 'com.victronenergy.system'
			self._dbusservice['/Enabled'] = 1
			# Set relay state.
			super()._update_remote_switch()
		# If there's no helper relay but the genset has '/Start', the start/stop service is also enabled.
		elif self._dbusmonitor.seen(self._remoteservice, '/Start'):
			self._dbusservice['/Enabled'] = 1
			self._helperrelayservice = None
		# If the genset does not have '/Start' and there is also no helper relay, disable the start/stop service.
		else:
			self._dbusservice['/Enabled'] = 0
			self._set_remote_switch_state(0)
			self._helperrelayservice = None

	def dbus_value_changed(self, dbusServiceName, dbusPath, options, changes, deviceInstance):
		if self._dbusservice is None:
			return

		if '/Settings/Relay/Function' in dbusPath:
			self._check_enable_conditions(changes['Value'])
		if '/StatusCode' in dbusPath:
			self._check_if_running(changes['Value'])

		super().dbus_value_changed(dbusServiceName, dbusPath, options, changes, deviceInstance)

		# Make sure that the relay polarity is set to normally open.
		if self._helperrelayservice is not None and self._dbusmonitor.get_value('com.victronenergy.settings', '/Settings/Relay/Polarity') == 1:
			self._dbusmonitor.set_value('com.victronenergy.settings', '/Settings/Relay/Polarity', 0)

	def _check_if_running(self, statusCode):
		if statusCode is not None:
			if 1 <= statusCode <= 9:
				super()._generator_started()
			else:
				super()._generator_stopped()

	def _get_remote_switch_state(self):
		# Do not drive the remote switch in case of error
		# because Fischer Panda genset will clear the error when switched off
		if self.get_error() in [Errors.REMOTEDISABLED, Errors.REMOTEINFAULT]:
			return 0
		if (not self._dbusservice['/Enabled']):
			return 0
		if self._helperrelayservice is not None:
			return self._dbusmonitor.get_value(self._helperrelayservice, '/Relay/0/State')
		else:
			return self._dbusmonitor.get_value(self._remoteservice, '/Start')

	def _set_remote_switch_state(self, value):
		error = self._dbusservice['/Error']
		# Do not drive the remote switch in case of error
		# because the generator clears the error when switched off
		if error in [Errors.REMOTEDISABLED, Errors.REMOTEINFAULT]:
			return
		self._dbusmonitor.set_value_async(self._remoteservice, '/Start', value)

		if not self._count_runtime_with_genset:
			super()._generator_started() if value else super()._generator_stopped()

		if (self._helperrelayservice):
			self._dbusmonitor.set_value_async(self._helperrelayservice, '/Relay/0/State', value)

class DcGenset(Genset):
	_connected = False

	def _set_remote_switch_state(self, value):
		super()._set_remote_switch_state(value)
		self._reset_power_input_timer()
		self._connected = False

	@property
	def dc_genset_current(self):
		return self._dbusmonitor.get_value(self._remoteservice, '/Dc/0/Current')

	@property
	def connected(self):
		if not self._connected:
			current = self.dc_genset_current
			# Consider the genset connected if it does not report current.
			self._connected = True if current is None else  current > self.DC_GENSET_CURRENT_THRESHOLD
		return self._connected

	def _remote_setup(self):
		super()._remote_setup()
		self._dbusservice['/Alarms/NoGeneratorAtDcIn'] = 0

		# Consider a connected DC genset to be running if the current is above this threshold
		self.DC_GENSET_CURRENT_THRESHOLD = 5

	def _detect_generator_at_input(self):
		if self._settings['nogeneratoratdcinalarm'] == 0 or \
				self._dbusservice['/State'] in [States.STOPPED, States.COOLDOWN, States.WARMUP]:
			return

		current = self.dc_genset_current
		if current is None:
			return

		if self.connected:
			if self._power_input_timer['unabletostart']:
				self.log_info('Generator detected at DC, alarm removed')
			self._reset_power_input_timer()
		elif self._power_input_timer['timeout'] < self.RETRIES_ON_ERROR:
			self._power_input_timer['timeout'] += 1
		elif not self._power_input_timer['unabletostart']:
			self._power_input_timer['unabletostart'] = True
			self._dbusservice['/Alarms/NoGeneratorAtDcIn'] = 2
			self.log_info('Generator not detected at DC, triggering alarm')

	def _reset_power_input_timer(self):
		super()._reset_power_input_timer()
		self._dbusservice['/Alarms/NoGeneratorAtDcIn'] = 0