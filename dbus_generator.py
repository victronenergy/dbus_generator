#!/usr/bin/python -u
# -*- coding: utf-8 -*-

# Function
# dbus_generator monitors the dbus for batteries (com.victronenergy.battery.*) and
# vebus com.victronenergy.vebus.*
# Battery and vebus monitors can be configured through the gui.
# It then monitors SOC, AC loads, battery current and battery voltage,to auto start/stop the generator based
# on the configuration settings. Generator can be started manually or periodically setting a tes trun period.
# Time zones function allows to use different values for the conditions along the day depending on time

from dbus.mainloop.glib import DBusGMainLoop
import gobject
import dbus
import dbus.service
import datetime
import calendar
import platform
import argparse
import time
import sys
import json
import os
from os import environ
import monotonic_time
# Victron packages
sys.path.insert(1, os.path.join(os.path.dirname(__file__), 'ext', 'velib_python'))
from vedbus import VeDbusService
from ve_utils import exit_on_error
from dbusmonitor import DbusMonitor
from settingsdevice import SettingsDevice
from logger import setup_logging

softwareversion = '1.3.2'
dbusgenerator = None


class Generator:

	def __init__(self):
		self._bus = dbus.SystemBus() if (platform.machine() == 'armv7l'
											or 'DBUS_SESSION_BUS_ADDRESS' not in environ) else dbus.SessionBus()
		self.HISTORY_DAYS = 30
		# One second per retry
		self.RETRIES_ON_ERROR = 300
		self._testrun_soc_retries = 0
		self._last_counters_check = 0
		self._dbusservice = None
		self._starttime = 0
		self._manualstarttimer = 0
		self._last_runtime_update = 0
		self._timer_runnning = 0
		self._battery_service = None
		self._battery_prefix = None
		self._vebusservice = None

		self._condition_stack = {
			'batteryvoltage': {
				'name': 'batteryvoltage',
				'reached': False,
				'boolean': False,
				'timed': True,
				'start_timer': 0,
				'stop_timer': 0,
				'valid': True,
				'enabled': False,
				'retries': 0,
				'monitoring': 'battery'
			},
			'batterycurrent': {
				'name': 'batterycurrent',
				'reached': False,
				'boolean': False,
				'timed': True,
				'start_timer': 0,
				'stop_timer': 0,
				'valid': True,
				'enabled': False,
				'retries': 0,
				'monitoring': 'battery'
			},
			'acload': {
				'name': 'acload',
				'reached': False,
				'boolean': False,
				'timed': True,
				'start_timer': 0,
				'stop_timer': 0,
				'valid': True,
				'enabled': False,
				'retries': 0,
				'monitoring': 'vebus'
			},
			'inverterhightemp': {
				'name': 'inverterhightemp',
				'reached': False,
				'boolean': True,
				'timed': True,
				'start_timer': 0,
				'stop_timer': 0,
				'valid': True,
				'enabled': False,
				'retries': 0,
				'monitoring': 'vebus'
			},
			'inverteroverload': {
				'name': 'inverteroverload',
				'reached': False,
				'boolean': True,
				'timed': True,
				'start_timer': 0,
				'stop_timer': 0,
				'valid': True,
				'enabled': False,
				'retries': 0,
				'monitoring': 'vebus'
			},
			'soc': {
				'name': 'soc',
				'reached': False,
				'boolean': False,
				'timed': False,
				'valid': True,
				'enabled': False,
				'retries': 0,
				'monitoring': 'battery'
			},
			'stoponac1': {
				'name': 'stoponac1',
				'reached': False,
				'boolean': True,
				'timed': False,
				'valid': True,
				'enabled': False,
				'retries': 0,
				'monitoring': 'vebus'
			}
		}

		# DbusMonitor expects these values to be there, even though we don need them. So just
		# add some dummy data. This can go away when DbusMonitor is more generic.
		dummy = {'code': None, 'whenToLog': 'configChange', 'accessLevel': None}

		dbus_tree = {
			'com.victronenergy.settings': {   # This is not our setting so do it here. not in supportedSettings
				'/Settings/Relay/Function': dummy,
				'/Settings/Relay/Polarity': dummy,
				'/Settings/System/TimeZone': dummy,
				'/Settings/System/AcInput1': dummy,
				'/Settings/System/AcInput2': dummy,
				'/Settings/Relay/Polarity': dummy
				},
			'com.victronenergy.battery': {
				'/Dc/0/Voltage': dummy,
				'/Dc/0/Current': dummy,
				'/Dc/1/Voltage': dummy,
				'/Dc/1/Current': dummy,
				'/Soc': dummy
				},
			'com.victronenergy.vebus': {
				'/Ac/Out/L1/P': dummy,
				'/Ac/Out/L2/P': dummy,
				'/Ac/Out/L3/P': dummy,
				'/Ac/ActiveIn/ActiveInput': dummy,
				'/Ac/ActiveIn/Connected': dummy,
				'/Dc/0/Voltage': dummy,
				'/Dc/0/Current': dummy,
				'/Dc/1/Voltage': dummy,
				'/Dc/1/Current': dummy,
				'/Soc': dummy,
				'/Alarms/HighTemperature': dummy,
				'/Alarms/Overload': dummy
				},
			'com.victronenergy.system': {
				'/Ac/Consumption/L1/Power': dummy,
				'/Ac/Consumption/L2/Power': dummy,
				'/Ac/Consumption/L3/Power': dummy,
				'/Dc/Pv/Power': dummy,
				'/AutoSelectedBatteryMeasurement': dummy,
				'/Ac/ActiveIn/Source': dummy,
				'/VebusService': dummy,
				'/Relay/0/State': dummy
				}
		}

		self._dbusmonitor = self._create_dbus_monitor(dbus_tree, valueChangedCallback=self._dbus_value_changed,
			deviceAddedCallback=self._device_added, deviceRemovedCallback=self._device_removed)

		supported_settings = {
				'autostart': ['/Settings/Generator0/AutoStartEnabled', 1, 0, 1],
				'stopwhengridavailable': ['/Settings/Generator0/StopWhenGridAvailable', 0, 0, 0],
				'accumulateddaily': ['/Settings/Generator0/AccumulatedDaily', '', 0, 0],
				'accumulatedtotal': ['/Settings/Generator0/AccumulatedTotal', 0, 0, 0],
				'batterymeasurement': ['/Settings/Generator0/BatteryService', 'default', 0, 0],
				'minimumruntime': ['/Settings/Generator0/MinimumRuntime', 0, 0, 86400],  # minutes
				'stoponac1enabled': ['/Settings/Generator0/StopWhenAc1Available', 0, 0, 10],
				# On permanent loss of communication: 0 = Stop, 1 = Start, 2 = keep running
				'onlosscommunication': ['/Settings/Generator0/OnLossCommunication', 0, 0, 2],
				# Quiet hours
				'quiethoursenabled': ['/Settings/Generator0/QuietHours/Enabled', 0, 0, 1],
				'quiethoursstarttime': ['/Settings/Generator0/QuietHours/StartTime', 75600, 0, 86400],
				'quiethoursendtime': ['/Settings/Generator0/QuietHours/EndTime', 21600, 0, 86400],
				# SOC
				'socenabled': ['/Settings/Generator0/Soc/Enabled', 0, 0, 1],
				'socstart': ['/Settings/Generator0/Soc/StartValue', 80, 0, 100],
				'socstop': ['/Settings/Generator0/Soc/StopValue', 90, 0, 100],
				'qh_socstart': ['/Settings/Generator0/Soc/QuietHoursStartValue', 90, 0, 100],
				'qh_socstop': ['/Settings/Generator0/Soc/QuietHoursStopValue', 90, 0, 100],
				# Voltage
				'batteryvoltageenabled': ['/Settings/Generator0/BatteryVoltage/Enabled', 0, 0, 1],
				'batteryvoltagestart': ['/Settings/Generator0/BatteryVoltage/StartValue', 11.5, 0, 150],
				'batteryvoltagestop': ['/Settings/Generator0/BatteryVoltage/StopValue', 12.4, 0, 150],
				'batteryvoltagestarttimer': ['/Settings/Generator0/BatteryVoltage/StartTimer', 20, 0, 10000],
				'batteryvoltagestoptimer': ['/Settings/Generator0/BatteryVoltage/StopTimer', 20, 0, 10000],
				'qh_batteryvoltagestart': ['/Settings/Generator0/BatteryVoltage/QuietHoursStartValue', 11.9, 0, 100],
				'qh_batteryvoltagestop': ['/Settings/Generator0/BatteryVoltage/QuietHoursStopValue', 12.4, 0, 100],
				# Current
				'batterycurrentenabled': ['/Settings/Generator0/BatteryCurrent/Enabled', 0, 0, 1],
				'batterycurrentstart': ['/Settings/Generator0/BatteryCurrent/StartValue', 10.5, 0.5, 10000],
				'batterycurrentstop': ['/Settings/Generator0/BatteryCurrent/StopValue', 5.5, 0, 10000],
				'batterycurrentstarttimer': ['/Settings/Generator0/BatteryCurrent/StartTimer', 20, 0, 10000],
				'batterycurrentstoptimer': ['/Settings/Generator0/BatteryCurrent/StopTimer', 20, 0, 10000],
				'qh_batterycurrentstart': ['/Settings/Generator0/BatteryCurrent/QuietHoursStartValue', 20.5, 0, 10000],
				'qh_batterycurrentstop': ['/Settings/Generator0/BatteryCurrent/QuietHoursStopValue', 15.5, 0, 10000],
				# AC load
				'acloadenabled': ['/Settings/Generator0/AcLoad/Enabled', 0, 0, 1],
				# Measuerement, 0 = Total AC consumption, 1 = AC on inverter output, 2 = Single phase
				'acloadmeasuerment': ['/Settings/Generator0/AcLoad/Measurement', 0, 0, 100],
				'acloadstart': ['/Settings/Generator0/AcLoad/StartValue', 1600, 5, 100000],
				'acloadstop': ['/Settings/Generator0/AcLoad/StopValue', 800, 0, 100000],
				'acloadstarttimer': ['/Settings/Generator0/AcLoad/StartTimer', 20, 0, 10000],
				'acloadstoptimer': ['/Settings/Generator0/AcLoad/StopTimer', 20, 0, 10000],
				'qh_acloadstart': ['/Settings/Generator0/AcLoad/QuietHoursStartValue', 1900, 0, 100000],
				'qh_acloadstop': ['/Settings/Generator0/AcLoad/QuietHoursStopValue', 1200, 0, 100000],
				# VE.Bus high temperature
				'inverterhightempenabled': ['/Settings/Generator0/InverterHighTemp/Enabled', 0, 0, 1],
				'inverterhightempstarttimer': ['/Settings/Generator0/InverterHighTemp/StartTimer', 20, 0, 10000],
				'inverterhightempstoptimer': ['/Settings/Generator0/InverterHighTemp/StopTimer', 20, 0, 10000],
				# VE.Bus overload
				'inverteroverloadenabled': ['/Settings/Generator0/InverterOverload/Enabled', 0, 0, 1],
				'inverteroverloadstarttimer': ['/Settings/Generator0/InverterOverload/StartTimer', 20, 0, 10000],
				'inverteroverloadstoptimer': ['/Settings/Generator0/InverterOverload/StopTimer', 20, 0, 10000],
				# TestRun
				'testrunenabled': ['/Settings/Generator0/TestRun/Enabled', 0, 0, 1],
				'testrunstartdate': ['/Settings/Generator0/TestRun/StartDate', time.time(), 0, 10000000000.1],
				'testrunstarttimer': ['/Settings/Generator0/TestRun/StartTime', 54000, 0, 86400],
				'testruninterval': ['/Settings/Generator0/TestRun/Interval', 28, 1, 365],
				'testrunruntime': ['/Settings/Generator0/TestRun/Duration', 7200, 1, 86400],
				'testrunskipruntime': ['/Settings/Generator0/TestRun/SkipRuntime', 0, 0, 100000],
				'testruntillbatteryfull': ['/Settings/Generator0/TestRun/RunTillBatteryFull', 0, 0, 1]
			}

		# Connect to localsettings
		self._settings = self._create_settings(supported_settings, self._handlechangedsetting)

		# Set timezone to user selected timezone
		tz = self._dbusmonitor.get_value('com.victronenergy.settings', '/Settings/System/TimeZone')
		environ['TZ'] = tz if tz else 'UTC'

		self._evaluate_if_we_are_needed()
		gobject.timeout_add(1000, exit_on_error, self._handletimertick)

	def _evaluate_if_we_are_needed(self):
		if self._dbusmonitor.get_value('com.victronenergy.settings', '/Settings/Relay/Function') == 1:
			if self._dbusmonitor.get_item('com.victronenergy.system', '/Relay/0/State') is None:
				logger.info('Systemcalc is not available yet, waiting...')

				if self._dbusservice is None:
					logger.info('Action! Going on dbus and taking control of the relay.')

				else:
					# As is not possible to keep the relay state during the CCGX power cycles,
					# set the relay polarity to normally open.
					relay_polarity = self._dbusmonitor.get_item('com.victronenergy.settings', '/Settings/Relay/Polarity')
					if relay_polarity.get_value() == 1:
						relay_polarity.set_value(dbus.Int32(0, variant_level=1))
						logger.info('Setting relay polarity to normally open.')

					# put ourselves on the dbus
					self._dbusservice = self._create_dbus_service()

					# State: None = invalid, 0 = stopped, 1 = running
					self._dbusservice.add_path('/State', value=0)
					# Condition that made the generator start
					self._dbusservice.add_path('/RunningByCondition', value='')
					# Runtime
					self._dbusservice.add_path('/Runtime', value=0, gettextcallback=self._gettext)
					# Today runtime
					self._dbusservice.add_path('/TodayRuntime', value=0, gettextcallback=self._gettext)
					# Test run runtime
					self._dbusservice.add_path('/TestRunIntervalRuntime',
												value=self._interval_runtime(self._settings['testruninterval']),
												gettextcallback=self._gettext)
					# Next tes trun date, values is 0 for test run disabled
					self._dbusservice.add_path('/NextTestRun', value=None, gettextcallback=self._gettext)
					# Next tes trun is needed 1, not needed 0
					self._dbusservice.add_path('/SkipTestRun', value=None)
					# Manual start
					self._dbusservice.add_path('/ManualStart', value=0, writeable=True)
					# Manual start timer
					self._dbusservice.add_path('/ManualStartTimer', value=0, writeable=True)
					# Silent mode active
					self._dbusservice.add_path('/QuietHours', value=0)
					self._determineservices()
					self._update_relay()

			else:
				if self._dbusservice is not None:
					self._stop_generator()
					self._dbusservice.__del__()
					self._dbusservice = None
					# Reset conditions
					for condition in self._condition_stack:
						self._reset_condition(self._condition_stack[condition])
					logger.info('Relay function is no longer set to generator start/stop: made sure generator is off ' +
								'and now going off dbus')

	def _device_added(self, dbusservicename, instance):
		self._evaluate_if_we_are_needed()
		self._determineservices()

	def _device_removed(self, dbusservicename, instance):
		self._evaluate_if_we_are_needed()
		self._determineservices()

	def _dbus_value_changed(self, dbusServiceName, dbusPath, options, changes, deviceInstance):
		if dbusPath == '/AutoSelectedBatteryMeasurement' and self._settings['batterymeasurement'] == 'default':
			self._determineservices()

		if dbusPath == '/VebusService':
			self._determineservices()

		if dbusPath == '/Settings/Relay/Function':
			self._evaluate_if_we_are_needed()

		# Update relay state when polarity is changed
		if dbusPath == '/Settings/Relay/Polarity':
			self._update_relay()

	def _handlechangedsetting(self, setting, oldvalue, newvalue):
		self._evaluate_if_we_are_needed()
		if setting == 'batterymeasurement':
			self._determineservices()
			# Reset retries and valid if service changes
			for condition in self._condition_stack:
				if self._condition_stack[condition]['monitoring'] == 'battery':
					self._condition_stack[condition]['valid'] = True
					self._condition_stack[condition]['retries'] = 0

		if setting == 'autostart':
				logger.info('Autostart function %s.' % ('enabled' if newvalue == 1 else 'disabled'))
		if self._dbusservice is not None and setting == 'testruninterval':
			self._dbusservice['/TestRunIntervalRuntime'] = self._interval_runtime(
															self._settings['testruninterval'])

	def _dbus_name_owner_changed(self, name, oldowner, newowner):
		self._determineservices()

	def _gettext(self, path, value):
		if path == '/NextTestRun':
			# Locale format date
			d = datetime.datetime.fromtimestamp(value)
			return d.strftime('%c')
		elif path in ['/Runtime', '/TestRunIntervalRuntime', '/TodayRuntime']:
			m, s = divmod(value, 60)
			h, m = divmod(m, 60)
			return '%dh, %dm, %ds' % (h, m, s)
		else:
			return value

	def _handletimertick(self):
		# try catch, to make sure that we kill ourselves on an error. Without this try-catch, there would
		# be an error written to stdout, and then the timer would not be restarted, resulting in a dead-
		# lock waiting for manual intervention -> not good!
		try:
			if self._dbusservice is not None:
				self._evaluate_startstop_conditions()
		except:
			self._stop_generator()
			import traceback
			traceback.print_exc()
			sys.exit(1)
		return True


	def _evaluate_startstop_conditions(self):

		# Conditions will be evaluated in this order
		conditions = ['soc', 'acload', 'batterycurrent', 'batteryvoltage', 'inverterhightemp', 'inverteroverload', 'stoponac1']
		start = False
		startbycondition = None
		activecondition = self._dbusservice['/RunningByCondition']
		today = calendar.timegm(datetime.date.today().timetuple())
		self._timer_runnning = False
		values = self._get_updated_values()
		connection_lost = False

		self._check_quiet_hours()

		# New day, register it
		if self._last_counters_check < today and self._dbusservice['/State'] == 0:
			self._last_counters_check = today
			self._update_accumulated_time()

		# Update current and accumulated runtime.
		if self._dbusservice['/State'] == 1:
			mtime = monotonic_time.monotonic_time().to_seconds_double()
			self._dbusservice['/Runtime'] = int(mtime - self._starttime)
			# By performance reasons, accumulated runtime is only updated
			# once per 10s. When the generator stops is also updated.
			if self._dbusservice['/Runtime'] - self._last_runtime_update >= 10:
				self._update_accumulated_time()

		if self._evaluate_manual_start():
			startbycondition = 'manual'
			start = True

		# Autostart conditions will only be evaluated if the autostart functionality is enabled
		if self._settings['autostart'] == 1:

			if self._evaluate_testrun_condition():
				startbycondition = 'testrun'
				start = True

			# Evaluate value conditions
			for condition in conditions:
				start = self._evaluate_condition(self._condition_stack[condition], values[condition]) or start
				startbycondition = condition if start and startbycondition is None else startbycondition
				# Connection lost is set to true if the numbear of retries of one or more enabled conditions
				# >= RETRIES_ON_ERROR
				if self._condition_stack[condition]['enabled']:
					connection_lost = self._condition_stack[condition]['retries'] >= self.RETRIES_ON_ERROR

			if self._condition_stack['stoponac1']['reached'] and startbycondition not in ['manual', 'testrun']:
				start = False
				if self._dbusservice['/State'] == 1 and activecondition not in ['manual', 'testrun']:
					logger.info('AC input 1 available, stopping')

			# If none condition is reached check if connection is lost and start/keep running the generator
			# depending on '/OnLossCommunication' setting
			if not start and connection_lost:
				# Start always
				if self._settings['onlosscommunication'] == 1:
					start = True
					startbycondition = 'lossofcommunication'
				# Keep running if generator already started
				if self._dbusservice['/State'] == 1 and self._settings['onlosscommunication'] == 2:
					start = True
					startbycondition = 'lossofcommunication'

		if start:
			self._start_generator(startbycondition)
		elif (self._dbusservice['/Runtime'] >= self._settings['minimumruntime'] * 60
			  or activecondition == 'manual'):
			self._stop_generator()

	def _reset_condition(self, condition):
		condition['reached'] = False
		if condition['timed']:
			condition['start_timer'] = 0
			condition['stop_timer'] = 0

	def _check_condition(self, condition, value):
		name = condition['name']

		if self._settings[name + 'enabled'] == 0:
			if condition['enabled']:
				condition['enabled'] = False
				logger.info('Disabling (%s) condition' % name)
				condition['retries'] = 0
				condition['valid'] = True
				self._reset_condition(condition)
			return False

		elif not condition['enabled']:
			condition['enabled'] = True
			logger.info('Enabling (%s) condition' % name)

		if (condition['monitoring'] == 'battery') and (self._settings['batterymeasurement'] == 'nobattery'):
			return False

		if value is None and condition['valid']:
			if condition['retries'] >= self.RETRIES_ON_ERROR:
				logger.info('Error getting (%s) value, skipping evaluation till get a valid value' % name)
				self._reset_condition(condition)
				self._comunnication_lost = True
				condition['valid'] = False
			else:
				condition['retries'] += 1
				if condition['retries'] == 1 or (condition['retries'] % 10) == 0:
					logger.info('Error getting (%s) value, retrying(#%i)' % (name, condition['retries']))
			return False

		elif value is not None and not condition['valid']:
			logger.info('Success getting (%s) value, resuming evaluation' % name)
			condition['valid'] = True
			condition['retries'] = 0

		# Reset retries if value is valid
		if value is not None:
			condition['retries'] = 0

		return condition['valid']

	def _evaluate_condition(self, condition, value):
		name = condition['name']
		setting = ('qh_' if self._dbusservice['/QuietHours'] == 1 else '') + name
		startvalue = self._settings[setting + 'start'] if not condition['boolean'] else 1
		stopvalue = self._settings[setting + 'stop'] if not condition['boolean'] else 0

		# Check if the condition has to be evaluated
		if not self._check_condition(condition, value):
			# If generator is started by this condition and value is invalid
			# wait till RETRIES_ON_ERROR to skip the condition
			if condition['reached'] and condition['retries'] <= self.RETRIES_ON_ERROR:
				return True

			return False

		# As this is a generic evaluation method, we need to know how to compare the values
		# first check if start value should be greater than stop value and then compare
		start_is_greater = startvalue > stopvalue

		# When the condition is already reached only the stop value can set it to False
		start = condition['reached'] or (value >= startvalue if start_is_greater else value <= startvalue)
		stop = value <= stopvalue if start_is_greater else value >= stopvalue

		# Timed conditions must start/stop after the condition has been reached for a minimum
		# time.
		if condition['timed']:
			if not condition['reached'] and start:
				condition['start_timer'] += time.time() if condition['start_timer'] == 0 else 0
				start = time.time() - condition['start_timer'] >= self._settings[name + 'starttimer']
				condition['stop_timer'] *= int(not start)
				self._timer_runnning = True
			else:
				condition['start_timer'] = 0

			if condition['reached'] and stop:
				condition['stop_timer'] += time.time() if condition['stop_timer'] == 0 else 0
				stop = time.time() - condition['stop_timer'] >= self._settings[name + 'stoptimer']
				condition['stop_timer'] *= int(not stop)
				self._timer_runnning = True
			else:
				condition['stop_timer'] = 0

		condition['reached'] = start and not stop
		return condition['reached']

	def _evaluate_manual_start(self):
		if self._dbusservice['/ManualStart'] == 0:
			if self._dbusservice['/RunningByCondition'] == 'manual':
				self._dbusservice['/ManualStartTimer'] = 0
			return False

		start = True
		# If /ManualStartTimer has a value greater than zero will use it to set a stop timer.
		# If no timer is set, the generator will not stop until the user stops it manually.
		# Once started by manual start, each evaluation the timer is decreased
		if self._dbusservice['/ManualStartTimer'] != 0:
			self._manualstarttimer += time.time() if self._manualstarttimer == 0 else 0
			self._dbusservice['/ManualStartTimer'] -= int(time.time()) - int(self._manualstarttimer)
			self._manualstarttimer = time.time()
			start = self._dbusservice['/ManualStartTimer'] > 0
			self._dbusservice['/ManualStart'] = int(start)
			# Reset if timer is finished
			self._manualstarttimer *= int(start)
			self._dbusservice['/ManualStartTimer'] *= int(start)

		return start

	def _evaluate_testrun_condition(self):
		if self._settings['testrunenabled'] == 0:
			self._dbusservice['/SkipTestRun'] = None
			self._dbusservice['/NextTestRun'] = None
			return False

		today = datetime.date.today()
		runtillbatteryfull = self._settings['testruntillbatteryfull'] == 1
		soc = self._get_updated_values()['soc']
		batteryisfull = runtillbatteryfull and soc == 100

		try:
			startdate = datetime.date.fromtimestamp(self._settings['testrunstartdate'])
			starttime = time.mktime(today.timetuple()) + self._settings['testrunstarttimer']
		except ValueError:
			logger.debug('Invalid dates, skipping testrun')
			return False

		# If start date is in the future set as NextTestRun and stop evaluating
		if startdate > today:
			self._dbusservice['/NextTestRun'] = time.mktime(startdate.timetuple())
			return False

		start = False
		# If the accumulated runtime during the tes trun interval is greater than '/TestRunIntervalRuntime'
		# the tes trun must be skipped
		needed = (self._settings['testrunskipruntime'] > self._dbusservice['/TestRunIntervalRuntime']
					  or self._settings['testrunskipruntime'] == 0)
		self._dbusservice['/SkipTestRun'] = int(not needed)

		interval = self._settings['testruninterval']
		stoptime = (starttime + self._settings['testrunruntime']) if not runtillbatteryfull else (starttime + 60)
		elapseddays = (today - startdate).days
		mod = elapseddays % interval

		start = (not bool(mod) and (time.time() >= starttime) and (time.time() <= stoptime))

		if runtillbatteryfull:
			if soc is not None:
				self._testrun_soc_retries = 0
				start = (start or self._dbusservice['/RunningByCondition'] == 'testrun') and not batteryisfull
			elif self._dbusservice['/RunningByCondition'] == 'testrun':
				if self._testrun_soc_retries < self.RETRIES_ON_ERROR:
					self._testrun_soc_retries += 1
					start = True
					if (self._testrun_soc_retries % 10) == 0:
						logger.info('Test run failed to get SOC value, retrying(#%i)' % self._testrun_soc_retries)
				else:
					logger.info('Failed to get SOC after %i retries, terminating test run condition' % self._testrun_soc_retries)
					start = False
			else:
				start = False

		if not bool(mod) and (time.time() <= stoptime):
			self._dbusservice['/NextTestRun'] = starttime
		else:
			self._dbusservice['/NextTestRun'] = (time.mktime((today + datetime.timedelta(days=interval - mod)).timetuple()) +
												 self._settings['testrunstarttimer'])
		return start and needed

	def _check_quiet_hours(self):
		active = False
		if self._settings['quiethoursenabled'] == 1:
			# Seconds after today 00:00
			timeinseconds = time.time() - time.mktime(datetime.date.today().timetuple())
			quiethoursstart = self._settings['quiethoursstarttime']
			quiethoursend = self._settings['quiethoursendtime']

			# Check if the current time is between the start time and end time
			if quiethoursstart < quiethoursend:
				active = quiethoursstart <= timeinseconds and timeinseconds < quiethoursend
			else:  # End time is lower than start time, example Start: 21:00, end: 08:00
				active = not (quiethoursend < timeinseconds and timeinseconds < quiethoursstart)

		if self._dbusservice['/QuietHours'] == 0 and active:
			logger.info('Entering to quiet mode')

		elif self._dbusservice['/QuietHours'] == 1 and not active:
			logger.info('Leaving secondary quiet mode')

		self._dbusservice['/QuietHours'] = int(active)

		return active

	def _update_accumulated_time(self):
		seconds = self._dbusservice['/Runtime']
		accumulated = seconds - self._last_runtime_update

		self._settings['accumulatedtotal'] = int(self._settings['accumulatedtotal']) + accumulated
		# Using calendar to get timestamp in UTC, not local time
		today_date = str(calendar.timegm(datetime.date.today().timetuple()))

		# If something goes wrong getting the json string create a new one
		try:
			accumulated_days = json.loads(self._settings['accumulateddaily'])
		except ValueError:
			accumulated_days = {today_date: 0}

		if (today_date in accumulated_days):
			accumulated_days[today_date] += accumulated
		else:
			accumulated_days[today_date] = accumulated

		self._last_runtime_update = seconds

		# Keep the historical with a maximum of HISTORY_DAYS
		while len(accumulated_days) > self.HISTORY_DAYS:
			accumulated_days.pop(min(accumulated_days.keys()), None)

		# Upadate settings
		self._settings['accumulateddaily'] = json.dumps(accumulated_days, sort_keys=True)
		self._dbusservice['/TodayRuntime'] = self._interval_runtime(0)
		self._dbusservice['/TestRunIntervalRuntime'] = self._interval_runtime(self._settings['testruninterval'])

	def _interval_runtime(self, days):
		summ = 0
		try:
			daily_record = json.loads(self._settings['accumulateddaily'])
		except ValueError:
			return 0

		for i in range(days + 1):
			previous_day = calendar.timegm((datetime.date.today() - datetime.timedelta(days=i)).timetuple())
			if str(previous_day) in daily_record.keys():
				summ += daily_record[str(previous_day)] if str(previous_day) in daily_record.keys() else 0

		return summ

	def _get_updated_values(self):
		battery_service = self._battery_service if self._battery_service else ''
		battery_prefix = self._battery_prefix if self._battery_prefix else ''
		vebus_service = self._vebusservice if self._vebusservice else ''
		system_service = 'com.victronenergy.system'
		loadOnAcOut = []
		totalConsumption = []

		values = {
			'batteryvoltage': self._dbusmonitor.get_value(battery_service, battery_prefix + '/Voltage'),
			'batterycurrent': self._dbusmonitor.get_value(battery_service, battery_prefix + '/Current'),
			'soc': self._dbusmonitor.get_value(battery_service, '/Soc'),
			'inverterhightemp': self._dbusmonitor.get_value(vebus_service, '/Alarms/HighTemperature'),
			'inverteroverload': self._dbusmonitor.get_value(vebus_service, '/Alarms/Overload')
		}

		for phase in ['L1', 'L2', 'L3']:
			loadOnAcOut.append(self._dbusmonitor.get_value(vebus_service, ('/Ac/Out/%s/P' % phase)))
			totalConsumption.append(self._dbusmonitor.get_value(system_service, ('/Ac/Consumption/%s/Power' % phase)))

		# Toltal consumption
		if self._settings['acloadmeasuerment'] == 0:
			values['acload'] = sum(filter(None, totalConsumption))

		# Load on inverter AC out
		if self._settings['acloadmeasuerment'] == 1:
			values['acload'] = sum(filter(None, loadOnAcOut))

		# Highest phase load
		if self._settings['acloadmeasuerment'] == 2:
			values['acload'] = max(loadOnAcOut)

		# AC input 1
		activein = self._dbusmonitor.get_value(vebus_service, '/Ac/ActiveIn/ActiveInput')
		# Active input is connected
		connected = self._dbusmonitor.get_value(vebus_service, '/Ac/ActiveIn/Connected')
		if None not in (activein, connected):
			values['stoponac1'] = activein == 0 and connected == 1
		else:
			values['stoponac1'] = None

		# Invalidate if vebus is not available
		if loadOnAcOut[0] == None:
			values['acload'] = None

		if values['batterycurrent']:
			values['batterycurrent'] *= -1

		return values

	def _determineservices(self):
		# batterymeasurement is either 'default' or 'com_victronenergy_battery_288/Dc/0'.
		# In case it is set to default, we use the AutoSelected battery
		# measurement, given by SystemCalc.
		batterymeasurement = None
		newbatteryservice = None
		batteryprefix = ''
		selectedbattery = self._settings['batterymeasurement']
		vebusservice = None

		if selectedbattery == 'default':
			batterymeasurement = self._dbusmonitor.get_value('com.victronenergy.system', 
			'/AutoSelectedBatteryMeasurement')
		elif len(selectedbattery.split('/', 1)) == 2:  # Only very basic sanity checking..
			batterymeasurement = self._settings['batterymeasurement']
		elif selectedbattery == 'nobattery':
			batterymeasurement = None
		else:
			# Exception: unexpected value for batterymeasurement
			pass

		if batterymeasurement:
			batteryprefix = '/' + batterymeasurement.split('/', 1)[1]

		# Get the current battery servicename
		if self._battery_service:
			oldservice = self._battery_service
		else:
			oldservice = None

		if batterymeasurement:
			battery_instance = int(batterymeasurement.split('_', 3)[3].split('/')[0])
			newbatteryservice = self._get_servicename_by_instance(battery_instance)

		if newbatteryservice and newbatteryservice != oldservice:
			if selectedbattery == 'nobattery':
				logger.info('Battery monitoring disabled! Stop evaluating related conditions')
				self._battery_service = None
				self._battery_prefix = None
			logger.info('Battery service we need (%s) found! Using it for generator start/stop'
						% batterymeasurement)
			self._battery_service = newbatteryservice
			self._battery_prefix = batteryprefix
		elif not newbatteryservice and newbatteryservice != oldservice:
			logger.info('Error getting battery service!')
			self._battery_service = newbatteryservice
			self._battery_prefix = batteryprefix

		# Get the default VE.Bus service
		vebusservice = self._dbusmonitor.get_value('com.victronenergy.system', '/VebusService')
		if vebusservice:
			if self._vebusservice != vebusservice:
				self._vebusservice = vebusservice
				logger.info('Vebus service (%s) found! Using it for generator start/stop'
						% vebusservice)
		else:
			if self._vebusservice is not None:
				logger.info('Vebus service (%s) dissapeared! Stop evaluating related conditions'
							% self._vebusservice)
			else:
				logger.info('Error getting Vebus service!')
			self._vebusservice = None

	def _get_servicename_by_instance(self, instance):
		services = self._dbusmonitor.get_service_list()
		sv = None
		for i in services:
			if services[i] == instance:
				sv = i
		return sv

	def _start_generator(self, condition):
		state = self._dbusservice['/State']
		relay = self._dbusmonitor.get_item('com.victronenergy.system', '/Relay/0/State')
		systemcalc_relay_state = relay.get_value()

		# This function will start the generator in the case generator not
		# already running. When differs, the RunningByCondition is updated
		if state == 0 or systemcalc_relay_state != state:
			self._dbusservice['/State'] = 1
			self._update_relay()
			self._starttime = monotonic_time.monotonic_time().to_seconds_double()
			logger.info('Starting generator by %s condition' % condition)
		elif self._dbusservice['/RunningByCondition'] != condition:
			logger.info('Generator previously running by %s condition is now running by %s condition'
						% (self._dbusservice['/RunningByCondition'], condition))

		self._dbusservice['/RunningByCondition'] = condition

	def _stop_generator(self):
		state = self._dbusservice['/State']
		relay = self._dbusmonitor.get_item('com.victronenergy.system', '/Relay/0/State')
		systemcalc_relay_state = relay.get_value()

		if state == 1 or systemcalc_relay_state != state:
			self._dbusservice['/State'] = 0
			self._update_relay()
			logger.info('Stopping generator that was running by %s condition' %
						str(self._dbusservice['/RunningByCondition']))
			self._dbusservice['/RunningByCondition'] = ''
			self._update_accumulated_time()
			self._starttime = 0
			self._dbusservice['/Runtime'] = 0
			self._dbusservice['/ManualStartTimer'] = 0
			self._manualstarttimer = 0
			self._last_runtime_update = 0

	def _update_relay(self):

		# Relay polarity 0 = NO, 1 = NC
		polarity = bool(self._dbusmonitor.get_value('com.victronenergy.settings', '/Settings/Relay/Polarity'))
		w = int(not polarity) if bool(self._dbusservice['/State']) else int(polarity)
		self._dbusmonitor.get_item('com.victronenergy.system', '/Relay/0/State').set_value(dbus.Int32(w, variant_level=1))

	def _create_dbus_monitor(self, *args, **kwargs):
		raise Exception('This function should be overridden')

	def _create_settings(self, *args, **kwargs):
		raise Exception('This function should be overridden')

	def _create_dbus_service(self):
		raise Exception('This function should be overridden')

class DbusGenerator(Generator):
	def _create_dbus_monitor(self, *args, **kwargs):
		return DbusMonitor(*args, **kwargs)

	def _create_settings(self, *args, **kwargs):
		bus = dbus.SessionBus() if 'DBUS_SESSION_BUS_ADDRESS' in os.environ else dbus.SystemBus()
		return SettingsDevice(bus, *args, timeout=10, **kwargs)

	def _create_dbus_service(self):
		dbusservice = VeDbusService('com.victronenergy.generator.startstop0')
		dbusservice.add_mandatory_paths(
			processname=__file__,
			processversion=softwareversion,
			connection='generator',
			deviceinstance=0,
			productid=None,
			productname=None,
			firmwareversion=None,
			hardwareversion=None,
			connected=1)
		return dbusservice

if __name__ == '__main__':
	# Argument parsing
	parser = argparse.ArgumentParser(
		description='Start and stop a generator based on conditions'
	)

	parser.add_argument('-d', '--debug', help='set logging level to debug',
						action='store_true')

	args = parser.parse_args()

	print '-------- dbus_generator, v' + softwareversion + ' is starting up --------'
	logger = setup_logging(args.debug)

	# Have a mainloop, so we can send/receive asynchronous calls to and from dbus
	DBusGMainLoop(set_as_default=True)

	generator = DbusGenerator()
	# Start and run the mainloop
	mainloop = gobject.MainLoop()
	mainloop.run()
