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

# Victron packages
sys.path.insert(1, os.path.join(os.path.dirname(__file__), './ext/velib_python'))
from vedbus import VeDbusService
from vedbus import VeDbusItemImport
from ve_utils import exit_on_error
from dbusmonitor import DbusMonitor
from settingsdevice import SettingsDevice
from logger import setup_logging

softwareversion = '1.2.5'
dbusgenerator = None


class DbusGenerator:

	def __init__(self):
		self._bus = dbus.SystemBus() if (platform.machine() == 'armv7l') else dbus.SessionBus()
		self.RELAY_GPIO_FILE = '/sys/class/gpio/gpio182/value'
		self.HISTORY_DAYS = 30
		# Number of retries on error
		self.RETRIES_ON_ERROR = 300
		self._last_counters_check = 0
		self._dbusservice = None
		self._starttime = 0
		self._manualstarttimer = 0
		self._last_runtime_update = 0
		self.timer_runnning = 0
		self._battery_measurement_voltage_import = None
		self._battery_measurement_current_import = None
		self._battery_measurement_soc_import = None
		self._battery_measurement_available = True
		self._vebusservice_high_temperature_import = None
		self._vebusservice_overload_import = None
		self._vebusservice = None
		self._vebusservice_available = False

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
				'retries': 0
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
				'retries': 0
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
				'retries': 0
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
				'retries': 0
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
				'retries': 0
			},
			'soc': {
				'name': 'soc',
				'reached': False,
				'boolean': False,
				'timed': False,
				'valid': True,
				'enabled': False,
				'retries': 0
			}
		}

		# DbusMonitor expects these values to be there, even though we don need them. So just
		# add some dummy data. This can go away when DbusMonitor is more generic.
		dummy = {'code': None, 'whenToLog': 'configChange', 'accessLevel': None}

		# TODO: possible improvement: don't use the DbusMonitor it all, since we are only monitoring
		# a set of static values which will always be available. DbusMonitor watches for services
		# that come and go, and takes care of automatic signal subscribtions etc. etc: all not necessary
		# in this use case where we have fixed services names (com.victronenergy.settings, and c
		# com.victronenergy.system).
		self._dbusmonitor = DbusMonitor({
			'com.victronenergy.settings': {   # This is not our setting so do it here. not in supportedSettings
				'/Settings/Relay/Function': dummy,
				'/Settings/Relay/Polarity': dummy,
				'/Settings/System/TimeZone': dummy,
				},
			'com.victronenergy.system': {   # This is not our setting so do it here. not in supportedSettings
				'/Ac/Consumption/Total/Power': dummy,
				'/Ac/PvOnOutput/Total/Power': dummy,
				'/Ac/PvOnGrid/Total/Power': dummy,
				'/Ac/PvOnGenset/Total/Power': dummy,
				'/Dc/Pv/Power': dummy,
				'/AutoSelectedBatteryMeasurement': dummy,
				}
		}, self._dbus_value_changed, self._device_added, self._device_removed)

		# Set timezone to user selected timezone
		environ['TZ'] = self._dbusmonitor.get_value('com.victronenergy.settings', '/Settings/System/TimeZone')

		# Connect to localsettings
		self._settings = SettingsDevice(
			bus=self._bus,
			supportedSettings={
				'autostart': ['/Settings/Generator0/AutoStart', 1, 0, 1],
				'accumulateddaily': ['/Settings/Generator0/AccumulatedDaily', '', 0, 0],
				'accumulatedtotal': ['/Settings/Generator0/AccumulatedTotal', 0, 0, 0],
				'batterymeasurement': ['/Settings/Generator0/BatteryService', "default", 0, 0],
				'minimumruntime': ['/Settings/Generator0/MinimumRuntime', 0, 0, 86400],  # minutes
				# Quiet hours
				'quiethoursenabled': ['/Settings/Generator0/QuietHours/Enabled', 0, 0, 1],
				'quiethoursstarttime': ['/Settings/Generator0/QuietHours/StartTime', 75600, 0, 86400],
				'quiethoursendtime': ['/Settings/Generator0/QuietHours/EndTime', 21600, 0, 86400],
				# SOC
				'socenabled': ['/Settings/Generator0/Soc/Enabled', 0, 0, 1],
				'socstart': ['/Settings/Generator0/Soc/StartValue', 90, 0, 100],
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
				'batterycurrentstart': ['/Settings/Generator0/BatteryCurrent/StartValue', 10.5, 0.5, 1000],
				'batterycurrentstop': ['/Settings/Generator0/BatteryCurrent/StopValue', 5.5, 0, 1000],
				'batterycurrentstarttimer': ['/Settings/Generator0/BatteryCurrent/StartTimer', 20, 0, 10000],
				'batterycurrentstoptimer': ['/Settings/Generator0/BatteryCurrent/StopTimer', 20, 0, 10000],
				'qh_batterycurrentstart': ['/Settings/Generator0/BatteryCurrent/QuietHoursStartValue', 20.5, 0, 1000],
				'qh_batterycurrentstop': ['/Settings/Generator0/BatteryCurrent/QuietHoursStopValue', 15.5, 0, 1000],
				# AC load
				'acloadenabled': ['/Settings/Generator0/AcLoad/Enabled', 0, 0, 1],
				'acloadstart': ['/Settings/Generator0/AcLoad/StartValue', 1600, 5, 100000],
				'acloadstop': ['/Settings/Generator0/AcLoad/StopValue', 800, 0, 100000],
				'acloadstarttimer': ['/Settings/Generator0/AcLoad/StartTimer', 20, 0, 10000],
				'acloadstoptimer': ['/Settings/Generator0/AcLoad/StopTimer', 20, 0, 10000],
				'qh_acloadstart': ['/Settings/Generator0/AcLoad/QuietHoursStartValue', 1900, 0, 100000],
				'qh_acloadstop': ['/Settings/Generator0/AcLoad/QuietHoursStopValue', 1200, 0, 100000],
				'couplepvpower': ['/Settings/Generator0/AcLoad/CouplePvPower', 0, 0, 1],
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
				'testrunskipruntime': ['/Settings/Generator0/TestRun/SkipRuntime', 0, 0, 100000]
			},
			eventCallback=self._handle_changed_setting)

		# Whenever services come or go, we need to check if it was a service we use. Note that this
		# is a bit double: DbusMonitor does the same thing. But since we don't use DbusMonitor to
		# monitor for com.victronenergy.battery, .vebus, .charger or any other possible source of
		# battery data, it is necessary to monitor for changes in the available dbus services.
		self._bus.add_signal_receiver(self._dbus_name_owner_changed, signal_name='NameOwnerChanged')

		self._evaluate_if_we_are_needed()
		gobject.timeout_add(1000, self._handletimertick)
		self._update_relay()
		self._changed = True

	def _evaluate_if_we_are_needed(self):
		if self._dbusmonitor.get_value('com.victronenergy.settings', '/Settings/Relay/Function') == 1:
			if self._dbusservice is None:
				logger.info('Action! Going on dbus and taking control of the relay.')

				relay_polarity_import = VeDbusItemImport(
														 bus=self._bus, serviceName='com.victronenergy.settings',
														 path='/Settings/Relay/Polarity',
														 eventCallback=None, createsignal=True)

				# As is not possible to keep the relay state during the CCGX power cycles,
				# set the relay polarity to normally open.
				if relay_polarity_import.get_value() == 1:
					relay_polarity_import.set_value(0)
					logger.info('Setting relay polarity to normally open.')

				# put ourselves on the dbus
				self._dbusservice = VeDbusService('com.victronenergy.generator.startstop0')
				self._dbusservice.add_mandatory_paths(
					processname=__file__,
					processversion=softwareversion,
					connection='generator',
					deviceinstance=0,
					productid=None,
					productname=None,
					firmwareversion=None,
					hardwareversion=None,
					connected=1)
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

	def _device_removed(self, dbusservicename, instance):
		self._evaluate_if_we_are_needed()

	def _dbus_value_changed(self, dbusServiceName, dbusPath, options, changes, deviceInstance):
		if dbusPath == '/AutoSelectedBatteryMeasurement' and self._settings['batterymeasurement'] == 'default':
			self._determineservices()
		if dbusPath == '/Settings/Relay/Function':
			self._evaluate_if_we_are_needed()
		self._changed = True
		# Update relay state when polarity is changed
		if dbusPath == '/Settings/Relay/Polarity':
			self._update_relay()

	def _handle_changed_setting(self, setting, oldvalue, newvalue):
		self._changed = True
		self._evaluate_if_we_are_needed()
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
			self._changed = False
		except:
			self._stop_generator()
			import traceback
			traceback.print_exc()
			sys.exit(1)
		return True

	def _evaluate_startstop_conditions(self):

		# Conditions will be evaluated in this order
		conditions = ['soc', 'acload', 'batterycurrent', 'batteryvoltage', 'inverterhightemp', 'inverteroverload']
		start = False
		runningbycondition = None
		today = calendar.timegm(datetime.date.today().timetuple())
		self.timer_runnning = False
		values = self._get_updated_values()

		self._check_quiet_hours()

		# New day, register it
		if self._last_counters_check < today and self._dbusservice['/State'] == 0:
			self._last_counters_check = today
			self._update_accumulated_time()

		# Update current and accumulated runtime.
		if self._dbusservice['/State'] == 1:
			self._dbusservice['/Runtime'] = int(time.time() - self._starttime)
			# By performance reasons, accumulated runtime is only updated
			# once per 10s. When the generator stops is also updated.
			if self._dbusservice['/Runtime'] - self._last_runtime_update >= 10:
				self._update_accumulated_time()

		if self._evaluate_manual_start():
			runningbycondition = 'manual'
			start = True

		# Autostart conditions will only be evaluated if the autostart functionality is enabled
		if self._settings['autostart'] == 1:
			# Evaluate value conditions
			for condition in conditions:
				start = self._evaluate_condition(self._condition_stack[condition], values[condition]) or start
				runningbycondition = condition if start and runningbycondition is None else runningbycondition

			if self._evaluate_testrun_condition() and not start:
				runningbycondition = 'testrun'
				start = True

		if start:
			self._start_generator(runningbycondition)
		elif (self._dbusservice['/Runtime'] >= self._settings['minimumruntime'] * 60
			  or self._dbusservice['/RunningByCondition'] == 'manual'):
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
				self._reset_condition(condition)
			return False

		elif not condition['enabled']:
			condition['enabled'] = True
			logger.info('Enabling (%s) condition' % name)

		if value is None and condition['valid']:
			if condition['retries'] >= self.RETRIES_ON_ERROR or not condition['reached']:
				logger.info('Error getting (%s) value, skipping evaluation till get a valid value' % name)
				self._reset_condition(condition)
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
				self.timer_runnning = True
			else:
				condition['start_timer'] = 0

			if condition['reached'] and stop:
				condition['stop_timer'] += time.time() if condition['stop_timer'] == 0 else 0
				stop = time.time() - condition['stop_timer'] >= self._settings[name + 'stoptimer']
				condition['stop_timer'] *= int(not stop)
				self.timer_runnning = True
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
		stoptime = starttime + self._settings['testrunruntime']
		elapseddays = (today - startdate).days
		mod = elapseddays % interval
		start = (not bool(mod) and (time.time() >= starttime) and (time.time() <= stoptime))

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
		pvongenset = self._dbusmonitor.get_value('com.victronenergy.system', '/Ac/PvOnGenset/Total/Power')
		pvongrid = self._dbusmonitor.get_value('com.victronenergy.system', '/Ac/PvOnGrid/Total/Power')
		pvonoutput = self._dbusmonitor.get_value('com.victronenergy.system', '/Ac/PvOnOutput/Total/Power')
		pvondc = self._dbusmonitor.get_value('com.victronenergy.system', '/Dc/Pv/Power')
		totalpvpower = 0

		if self._settings['couplepvpower']:
			if pvongenset:
				totalpvpower += pvongenset
			if pvongrid:
				totalpvpower += pvongrid
			if pvonoutput:
				totalpvpower += pvonoutput
			if pvondc:
				totalpvpower += pvondc

		values = {
			'batteryvoltage': (self._battery_measurement_voltage_import.get_value()
							   if self._battery_measurement_voltage_import else None),
			'batterycurrent': (self._battery_measurement_current_import.get_value()
							   if self._battery_measurement_current_import else None),
			'soc': self._battery_measurement_soc_import.get_value() if self._battery_measurement_soc_import else None,
			'acload': self._dbusmonitor.get_value('com.victronenergy.system', '/Ac/Consumption/Total/Power'),
			'inverterhightemp': (self._vebusservice_high_temperature_import.get_value()
								 if self._vebusservice_high_temperature_import else None),
			'inverteroverload': (self._vebusservice_overload_import.get_value()
								 if self._vebusservice_overload_import else None)
		}

		if values['acload']:
			values['acload'] -= totalpvpower

		if values['batterycurrent']:
			values['batterycurrent'] *= -1

		return values

	def _determineservices(self):
		# batterymeasurement is either 'default' or 'com_victronenergy_battery_288/Dc/0'.
		# In case it is set to default, we use the AutoSelected battery measurement, given by
		# SystemCalc.

		batterymeasurement = None
		batteryservicename = None
		newbatteryservice = None
		batteryprefix = ""
		selectedbattery = self._settings['batterymeasurement']
		vebusservice = None

		if selectedbattery == 'default':
			batterymeasurement = self._dbusmonitor.get_value('com.victronenergy.system', '/AutoSelectedBatteryMeasurement')
		elif len(selectedbattery.split("/", 1)) == 2:  # Only very basic sanity checking..
			batterymeasurement = self._settings['batterymeasurement']
		elif selectedbattery == 'nobattery':
			batterymeasurement = None
		else:
			# Exception: unexpected value for batterymeasurement
			pass

		if batterymeasurement:
			batteryprefix = "/" + batterymeasurement.split("/", 1)[1]

		# Get the current battery servicename
		if self._battery_measurement_voltage_import:
			oldservice = (self._battery_measurement_voltage_import.serviceName +
						  self._battery_measurement_voltage_import.path.replace("/Voltage", ""))
		else:
			oldservice = None

		if batterymeasurement:
			batteryservicename = VeDbusItemImport(
				bus=self._bus,
				serviceName="com.victronenergy.system",
				path='/ServiceMapping/' + batterymeasurement.split("/", 1)[0],
				eventCallback=None,
				createsignal=False)

			if batteryservicename.get_value():
				newbatteryservice = batteryservicename.get_value() + batteryprefix
			else:
				newbatteryservice = None

		if batteryservicename and batteryservicename.get_value() and oldservice != newbatteryservice:
			self._battery_measurement_available = True

			logger.info('Battery service we need (%s) found! Using it for generator start/stop'
						% batterymeasurement)
			try:
				self._battery_measurement_voltage_import = VeDbusItemImport(
					bus=self._bus, serviceName=batteryservicename.get_value(),
					path=batteryprefix + '/Voltage', eventCallback=None, createsignal=True)

				self._battery_measurement_current_import = VeDbusItemImport(
					bus=self._bus, serviceName=batteryservicename.get_value(),
					path=batteryprefix + '/Current', eventCallback=None, createsignal=True)

				# Exception caused by Matthijs :), we forgot to batteryprefix the Soc during the big path-change...
				self._battery_measurement_soc_import = VeDbusItemImport(
					bus=self._bus, serviceName=batteryservicename.get_value(),
					path='/Soc', eventCallback=None, createsignal=True)
			except Exception:
				logger.debug('Error getting battery service!')
				self._battery_measurement_voltage_import = None
				self._battery_measurement_current_import = None
				self._battery_measurement_soc_import = None

		elif selectedbattery == 'nobattery' and self._battery_measurement_available:
			logger.info('Battery monitoring disabled! Stop evaluating related conditions')
			self._battery_measurement_voltage_import = None
			self._battery_measurement_current_import = None
			self._battery_measurement_soc_import = None
			self._battery_measurement_available = False

		elif batteryservicename and batteryservicename.get_value() is None and self._battery_measurement_available:
			logger.info('Battery service we need (%s) is not available! Stop evaluating related conditions'
						% batterymeasurement)
			self._battery_measurement_voltage_import = None
			self._battery_measurement_current_import = None
			self._battery_measurement_soc_import = None
			self._battery_measurement_available = False

		# Get the default VE.Bus service and import high temperature and overload warnings
		vebusservice = VeDbusItemImport(
				bus=self._bus,
				serviceName="com.victronenergy.system",
				path='/VebusService',
				eventCallback=None,
				createsignal=False)

		if vebusservice.get_value() and (vebusservice.get_value() != self._vebusservice
										 or not self._vebusservice_available):
			self._vebusservice = vebusservice.get_value()
			self._vebusservice_available = True

			logger.info('Vebus service (%s) found! Using it for generator start/stop'
						% vebusservice.get_value())
			try:
				self._vebusservice_high_temperature_import = VeDbusItemImport(
						bus=self._bus, serviceName=vebusservice.get_value(),
						path='/Alarms/HighTemperature', eventCallback=None, createsignal=True)

				self._vebusservice_overload_import = VeDbusItemImport(
						bus=self._bus, serviceName=vebusservice.get_value(),
						path='/Alarms/Overload', eventCallback=None, createsignal=True)
			except Exception:
				logger.info('Error getting Vebus service!')
				self._vebusservice_available = False
				self._vebusservice_high_temperature_import = None
				self._vebusservice_overload_import = None

		elif not vebusservice.get_value() and self._vebusservice_available:
			logger.info('Vebus service (%s) dissapeared! Stop evaluating related conditions'
						% self._vebusservice)
			self._vebusservice_available = False
			self._vebusservice_high_temperature_import = None
			self._vebusservice_overload_import = None

		# Trigger an immediate check of system status
		self._changed = True

	def _start_generator(self, condition):
		# This function will start the generator in the case generator not
		# already running. When differs, the RunningByCondition is updated
		if self._dbusservice['/State'] == 0:
			self._dbusservice['/State'] = 1
			self._update_relay()
			self._starttime = time.time()
			logger.info('Starting generator by %s condition' % condition)
		elif self._dbusservice['/RunningByCondition'] != condition:
			logger.info('Generator previously running by %s condition is now running by %s condition'
						% (self._dbusservice['/RunningByCondition'], condition))

		self._dbusservice['/RunningByCondition'] = condition

	def _stop_generator(self):
		if self._dbusservice['/State'] == 1:
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

		try:
			f = open(self.RELAY_GPIO_FILE, 'w')
			f.write(str(w))
			f.close()
		except IOError:
			logger.info('Error writting to the relay GPIO file!: %s' % self.RELAY_GPIO_FILE)


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
