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
		'/Dc/0/Voltage': dummy,
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

	def genset_added(self, dbusservicename, instance):
		pass

	def genset_removed(self, dbusservicename, instance):
		pass

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

	def genset_added(self, dbusservicename, instance):
		if dbusservicename.startswith('com.victronenergy.dcgenset') and self._remoteservice != dbusservicename:
			# Add settings for multiple DC gensets
			self._settings.addSettings({'nogeneratoratdcinalarm{}'.format(name): ['/Settings/{}/Alarms/NoGeneratorAtDcIn'.format(name), 0, 0, 1],
			# Setting to describe which gensets are enabled. String holding a comma-separated list of device instances, or 'all' or 'rotate' (use only one genset at a time, but rotate between them).
						'gensetsenabled{}'.format(name): ['/Settings/{}/MultipleGensets/GensetsEnabled'.format(name), "all", "", ""],
						'gensetsrotate{}'.format(name): ['/Settings/{}/MultipleGensets/LastRotated'.format(name), 0, 0, 0]})

			# Upgrade to DCGensets class
			self.__class__ = DcGensets
			this_instance = self._dbusmonitor.get_value(self._remoteservice, '/DeviceInstance')
			gensets = {this_instance: self._remoteservice, instance: dbusservicename}
			logging.info(f'Multiple DC gensets detected, upgrading to DcGensets class')

			# Add dbus paths for the genset services
			if '/MultipleGensets/GensetsDetected' not in self._dbusservice:
				self._dbusservice.add_path('/MultipleGensets/GensetsDetected', "", writeable=False)	# JSON list of genset services with their device instance and product id, e.g. [{"service": "com.victronenergy.dcgenset_1", "instance": 1}, {...}]
				self._dbusservice.add_path('/MultipleGensets/GensetsEnabled', "", writeable=True, onchangecallback=self._handle_changed_value)	# Proxy path to /GensetsEnabled setting
				self._dbusservice.add_path('/MultipleGensets/LastRotated', None, writeable=False)		# Proxy path to /LastRotated setting
				self._dbusservice.add_path('/MultipleGensets/Voltage', 0, writeable=False)
				self._dbusservice.add_path('/MultipleGensets/Current', 0, writeable=False)
				self._dbusservice.add_path('/MultipleGensets/Power', 0, writeable=False)

			self._remote_setup(gensets)

class GensetService():
	def __init__(self, _dbusmonitor, service_name):
		self._dbusmonitor = _dbusmonitor
		self.service_name = service_name

	@property
	def voltage(self):
		return self._dbusmonitor.get_value(self.service_name, '/Dc/0/Voltage')

	@property
	def current(self):
		return self._dbusmonitor.get_value(self.service_name, '/Dc/0/Current')

	@property
	def start(self):
		return self._dbusmonitor.get_value(self.service_name, '/Start')

	@start.setter
	def start(self, value):
		self._dbusmonitor.set_value_async(self.service_name, '/Start', value)

	@property
	def status_code(self):
		return self._dbusmonitor.get_value(self.service_name, '/StatusCode')

	@property
	def remote_start_enabled(self):
		return self._dbusmonitor.get_value(self.service_name, '/RemoteStartModeEnabled')

	@property
	def error(self):
		return self._dbusmonitor.get_value(self.service_name, '/Error/0/Id')


class DcGensets(DcGenset):
	_gensets = {}
	_genset_services = {}
	_rotate = False
	_dc_genset_total_current = 0

	# Used by _detect_generator_at_input to determine if a generator is detected at the input of the DC genset(s)
	# For multiple gensets, the alarm must be triggered when either of the gensets does not provide sufficient current,
	# so return the lowest current among the gensets to determine if a generator is detected at the input
	@property
	def dc_genset_current(self):
		# Filter out None values. If a genset does not report current, it is considered connected anyways.
		currents = [g.current for g in self._gensets.values() if g.status_code == 8 and g.current is not None]
		return min(currents) if len(currents) > 0 else 0

	def _start_genset(self, value):
		if not self._gensets or value is None:
			return

		if not self._rotate or value == 0 or len(self._gensets) == 1:
			# Start/Stop all gensets
			for g in self._gensets:
				self._start_one_genset(self._gensets[g], value)
			return

		if self._rotate:
			last_rotated = self._settings['gensetsrotate'] or 0
			last = last_rotated
			while True:
				next = None
				for g in self._rotation_order:
					if g > last:
						next = g
						break
				if next is None:
					next = self._rotation_order[0]
				logging.info(f'Trying to start genset with device instance {next}')
				if self._start_one_genset(self._gensets[next], 1):
					self._settings['gensetsrotate'] = next
					self._dbusservice['/MultipleGensets/LastRotated'] = next
					break
				else:
					last = next
					if last == last_rotated:
						logging.warning('None of the gensets could be started')
						break

	def _start_one_genset(self, genset, value):
		if not genset.error:
			genset.start = value
			return True
		return False

	def _handle_changed_value(self, path, value):
		if path == '/MultipleGensets/GensetsEnabled':
			value = str(value)
			if value != '' and value != 'all' and value != 'rotate' and not all(v.isdigit() for v in value.split(',')):
				return False
			if value != 'rotate':
				self._dbusservice['/MultipleGensets/LastRotated'] = None
			# This will invoke the handlechangedsetting callback
			self._settings['gensetsenabled'] = value
		return True

	def handlechangedsetting(self, setting, oldvalue, newvalue):
		if setting == 'gensetsenabled{}'.format(name):
			self._check_enable_conditions()

		super().handlechangedsetting(setting, oldvalue, newvalue)

	def _probe_gensets(self):
		# Check if the genset services list is still valid and remove the ones that are not there anymore.
		# Loop over a copy of the genset services dict so we can modify the original dict while looping over it.
		for instance, service in self._genset_services.copy().items():
			if self._dbusmonitor.seen(service, '/DeviceInstance'):
				# Double check if the instance is there
				device_instance = self._dbusmonitor.get_value(service, '/DeviceInstance')
				if device_instance != instance:
					del self._genset_services[instance]

	def _remote_setup(self, gensets = {}):
		if gensets:
			self._genset_services = gensets
		# Set paths
		json = [{"service": s, "instance": i} for i, s in self._genset_services.items()]
		self._dbusservice['/MultipleGensets/GensetsDetected'] = json
		self._dbusservice['/MultipleGensets/GensetsEnabled'] = self._settings['gensetsenabled']
		if self._dbusservice['/MultipleGensets/GensetsEnabled'] == 'rotate' and self._settings['gensetsrotate'] is not None:
			self._dbusservice['/MultipleGensets/LastRotated'] = self._settings['gensetsrotate']

		self.enable()
		self._check_enable_conditions()
		self._update_genset_aggregated_values()

	def _check_enable_conditions(self, relaysetting = None):
		# We don't do anything with the relay, but need the arg to remain compatible with the parent method signature
		self._gensets = {}
		gensets_enabled = self._settings['gensetsenabled']

		# No gensets enabled, do nothing
		if gensets_enabled == '':
			return

		logging.info(f'Checking enable conditions for DC gensets, enabled gensets: {gensets_enabled}')
		need_all = gensets_enabled == 'all' or gensets_enabled == 'rotate'
		self._rotate = (gensets_enabled == 'rotate')
		instances = [int(x) for x in gensets_enabled.split(',') if x.isdigit()] if not need_all else []

		# Update genset services list
		self._probe_gensets()
		if len(self._genset_services) <= 1:
			logging.warning(f'Only {len(self._genset_services)} genset(s) detected, downgrading to single genset control')
			self._downgrade_to_single_genset()
			return

		for instance, service in self._genset_services.items():
			if need_all or instance in instances:
				self._gensets[instance] = GensetService(self._dbusmonitor, service)

		if len(self._gensets) == 0:
			logging.warning('None of the desired gensets were found')
			self._dbusservice['/MultipleGensets/GensetsEnabled'] = ""
			self._settings['gensetsenabled'] = ""
			return

		if not need_all and len(instances) != len(self._gensets):
			logging.warning(f'Could not find the following gensets: {list(set(instances) - set(self._gensets.keys()))}, they will be ignored')

		if self._rotate:
			last_rotated = self._settings['gensetsrotate']
			if last_rotated is not None and last_rotated in self._gensets:
				self._dbusservice['/MultipleGensets/LastRotated'] = last_rotated
			else:
				# Last rotated genset instance stored in settings is not found. Reset the rotation.
				self._dbusservice['/MultipleGensets/LastRotated'] = None
				self._settings['gensetsrotate'] = 0
			self._rotation_order = tuple(sorted(self._gensets.keys()))
			logging.info(f'Rotation between gensets enabled, rotation order: {self._rotation_order}')

		if len(self._gensets) > 0:
			# Order gensets by device instance
			self._gensets = dict(sorted(self._gensets.items()))
			self._dbusservice['/Enabled'] = 1
		else:
			self._dbusservice['/Enabled'] = 0

		logging.info(f'Enabled gensets: {list(self._gensets.keys())} with rotation: {self._rotate}')

	def _check_if_running(self, status_code = None):
		if any(self._gensets[g].status_code in range(1, 10) for g in self._gensets):
			super()._generator_started()
		else:
			super()._generator_stopped()

	def _update_genset_aggregated_values(self):
		gensets = [g for g in self._gensets.values() if g.status_code == 8]
		# Update total power/voltage/current for all gensets
		voltages = [g.voltage for g in gensets if g.voltage is not None]
		currents = [g.current for g in gensets if g.current is not None]
		voltage = sum(voltages)/len(voltages) if len(voltages) > 0 else 0
		current = sum(currents)
		self._dbusservice['/MultipleGensets/Voltage'] = voltage
		self._dbusservice['/MultipleGensets/Current'] = current
		self._dbusservice['/MultipleGensets/Power'] = voltage * current

	def dbus_value_changed(self, dbusServiceName, dbusPath, options, changes, deviceInstance):
		if self._dbusservice is None:
			return

		if dbusServiceName not in self._genset_services.values():
			return

		if '/DeviceInstance' in dbusPath and dbusServiceName in self._genset_services.values():
			logging.info(f'Genset service {dbusServiceName} has changed device instance to {changes["Value"]}, updating genset services list')
			self._genset_services[changes['Value']] = dbusServiceName
			self._check_enable_conditions()

		if any(x in dbusPath for x in ['/Dc/0/Voltage', '/Dc/0/Current', '/Dc/0/Power']):
			self._update_genset_aggregated_values()

		super().dbus_value_changed(dbusServiceName, dbusPath, options, changes, deviceInstance)

	def _check_remote_status(self):
		error = self.get_error()

		if len(self._gensets) == 0:
			# No gensets enabled, set error
			self.set_error(Errors.NO_GENSETS_ENABLED)
			return
		elif error == Errors.NO_GENSETS_ENABLED:
			self.clear_error()

		# Check for genset error, also accept absence of the error path as valid no-error condition
		# Only when all gensets report an error, the overall status is error
		remotestart = any(self._gensets[g].remote_start_enabled for g in self._gensets)
		genset_error = all(self._gensets[g].error for g in self._gensets)
		if genset_error:
			self.set_error(Errors.REMOTEINFAULT)
		elif error == Errors.REMOTEINFAULT:
			self.clear_error()

		if not remotestart and error == Errors.NONE:
			self.set_error(Errors.REMOTEDISABLED)
		elif remotestart and error == Errors.REMOTEDISABLED:
			self.clear_error()

	def _get_remote_switch_state(self):
		# Do not drive the remote switch in case of error
		# because Fischer Panda genset will clear the error when switched off
		if self.get_error() in [Errors.REMOTEDISABLED, Errors.REMOTEINFAULT]:
			return 0
		if (not self._dbusservice['/Enabled']):
			return 0
		return any(self._gensets[g].start for g in self._gensets)

	def _set_remote_switch_state(self, value):
		error = self.get_error()
		# Do not drive the remote switch in case of error
		# because the generator clears the error when switched off
		if error in [Errors.REMOTEDISABLED, Errors.REMOTEINFAULT]:
			return

		self._reset_power_input_timer()
		self._connected = False
		self._start_genset(value)

		super()._generator_started() if value else super()._generator_stopped()

	def genset_added(self, dbusservicename, instance):
		if dbusservicename.startswith('com.victronenergy.dcgenset'):
			logging.info(f'New DC genset service {dbusservicename} detected with instance {instance}, adding to genset service list')
			self._genset_services[instance] = dbusservicename
			self._remote_setup()

	def genset_removed(self, dbusservicename):
		logging.info(f'DC genset service {dbusservicename}, removing from genset service list')
		if dbusservicename.startswith('com.victronenergy.dcgenset'):
			for i, s in self._genset_services.items():
				if s == dbusservicename:
					del self._genset_services[i]
					break
			if len(self._genset_services) == 1:
				self._downgrade_to_single_genset()
				return
		self._remote_setup()

	def _downgrade_to_single_genset(self):
		# Downgrade to DCGenset class if only one genset remains
		logging.info(f'Downgrading to single DC genset control since only one genset remains')
		self.__class__ = DcGenset

		# Clear multiple gensets paths
		self._dbusservice['/MultipleGensets/GensetsDetected'] = None
		self._dbusservice['/MultipleGensets/GensetsEnabled'] = None
		self._dbusservice['/MultipleGensets/LastRotated'] = None
		self._dbusservice['/MultipleGensets/Voltage'] = None
		self._dbusservice['/MultipleGensets/Current'] = None
		self._dbusservice['/MultipleGensets/Power'] = None
		self._remote_setup()
