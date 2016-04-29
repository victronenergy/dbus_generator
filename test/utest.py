#!/usr/bin/env python
# -*- coding: utf-8 -*-

import unittest
import dbus
from dbus.mainloop.glib import DBusGMainLoop
import platform
import random
import time
import calendar
import datetime
import json
import sys
import os
from subprocess import Popen, PIPE, STDOUT

# our own packages
sys.path.insert(1, os.path.join(os.path.dirname(__file__), '../ext/velib_python'))
from settingsdevice import SettingsDevice


class TestGenerator(unittest.TestCase):

	def setUp(self):
		self.start_services('vebus')
		self.start_services('battery')
		self.start_services('pvinverter')
		self.start_services('solarcharger')

		self.bus = dbus.SessionBus() if 'DBUS_SESSION_BUS_ADDRESS' in os.environ else dbus.SystemBus()

		settings = {attrs[0] : attrs for attrs in [
			['/Settings/System/TimeZone', 'Europe/Amsterdam', 0, 0],
			['/Settings/Relay/Polarity', 0, 0, 1],
			['/Settings/Relay/Function', 1, 0, 1],
			['/Settings/Generator0/BatteryService', 'com_victronenergy_battery_223/Dc/0', 0, 0],
			['/Settings/Generator0/QuietHours/Enabled', 0, 0, 1],
			['/Settings/Generator0/QuietHours/StartTime', 0, 0, 0],
			['/Settings/Generator0/QuietHours/EndTime', 0, 0, 0],
			['/Settings/Generator0/MinimumRuntime', 0, 0, 0],
			['/Settings/Generator0/TestRun/Enabled', 0, 0, 1],
			['/Settings/Generator0/TestRun/RunTillBatteryFull', 0, 0, 1],
			['/Settings/Generator0/TestRun/SkipRuntime', 0, 0, 0],
			['/Settings/Generator0/TestRun/StartDate', 0, 0, 0],
			['/Settings/Generator0/TestRun/StartTime', 0, 0, 0],
			['/Settings/Generator0/TestRun/Interval', 0, 0, 0],
			['/Settings/Generator0/TestRun/Duration', 0, 0, 0],
			['/Settings/Generator0/AutoStartEnabled', 1, 0, 1],
			['/Settings/Generator0/OnLossCommunication', 0, 0, 0],
			['/Settings/Generator0/AccumulatedDaily', '', 0, 0],
			['/Settings/Generator0/AccumulatedTotal', 0, 0, 0],
		]}
		conditions = ("BatteryCurrent", "BatteryVoltage", "AcLoad")
		condition_defaults  = {"StartValue": 0, "StopValue": 0, "StartTimer": 0, "StopTimer": 0,
			"Enabled": 0, "QuitHoursStartValue": 0, "QuitHoursStopValue": 0}
		for condition in conditions:
			for setting_suffix, default_value in condition_defaults.iteritems():
				setting_label = 'gen0' + condition + setting_suffix
				setting_path = '/Settings/Generator0/' + condition + '/' + setting_suffix
				settings[setting_label] = [setting_path, default_value, 0, 0]

		self.settings = SettingsDevice(
			bus=self.bus,
			supportedSettings=settings,
			eventCallback=self.handle_changed_setting
		)

		# dbusgenerator needs to be able to read the timezone setting, so the settings must already by added
		self.start_services('dbusgenerator')

		self._settingspath = 'com.victronenergy.settings'
		self._generatorpath = 'com.victronenergy.generator.startstop0'
		self.batteryservice = 'com.victronenergy.battery.tty22'
		self.vebusservice = 'com.victronenergy.vebus.tty23'
		self.solarchergerservice = 'com.victronenergy.solarcharger.tty33'
		self.pvinverterservice = 'com.victronenergy.pvinverter.test'

		self.retriesonerror = 300

		self.set_value(self._settingspath, "/Settings/Relay/Function", 1)
		self.fill_history()
		self.firstRun = False
		self.reset_all_conditons()
		if (platform.machine() == 'armv7l'):
			os.environ['TZ'] = self.get_value(self._settingspath, '/Settings/System/TimeZone')

	def handle_changed_setting(setting, old_val, new_val):
		pass

	def doCleanups(self):
		super(TestGenerator, self).doCleanups()
		self.stop_services()

	def start_services(self, service):
		if service == 'battery':
			self.batteryp = Popen([sys.executable, "dummybattery.py"], stdout=PIPE, stderr=STDOUT)
			while True:
				line = self.batteryp.stdout.readline()
				#print line.rstrip()
				if not line or ":/Soc" in line:
					break
		elif service == 'vebus':
			self.vebusp = Popen([sys.executable, "dummyvebus.py"], stdout=PIPE, stderr=STDOUT)
			while True:
				line = self.vebusp.stdout.readline()
				#print line.rstrip()
				if not line or ":/Soc" in line:
					break
		elif service == 'solarcharger':
			self.solarchargerp = Popen([sys.executable, "dummysolarcharger.py"], stdout=PIPE, stderr=STDOUT)
			while True:
				line = self.solarchargerp.stdout.readline()
				#print line.rstrip()
				if not line or "/Dc/0/Power: 291" in line:
					break
		elif service == 'pvinverter':
			self.pvinverterp = Popen([sys.executable, "dummypvinverter.py"], stdout=PIPE, stderr=STDOUT)
			while True:
				line = self.pvinverterp.stdout.readline()
				#print line.rstrip()
				if not line or ":/Ac/L3/Power" in line:
					break
		elif service == 'dbusgenerator':
			self.dbusgeneratorp = Popen([sys.executable, "../dbus_generator.py"], stdout=PIPE, stderr=STDOUT)
			while True:
				line = self.dbusgeneratorp.stdout.readline()
				#print line.rstrip()
				if not line or ":vedbus:registered" in line:
					break

	def stop_services(self):
		self.stop_battery_service()
		self.stop_vebus_service()
		self.stop_pvinverter_service()
		self.stop_solarcharger_service()
		self.stop_dbusgenerator_service()

	def stop_vebus_service(self):
		try:
			self.vebusp.kill()
			self.vebusp.wait()
		except (AttributeError, OSError):
			pass

	def stop_pvinverter_service(self):
		try:
			self.pvinverterp.kill()
			self.pvinverterp.wait()
		except (AttributeError, OSError):
			pass

	def stop_solarcharger_service(self):
		try:
			self.solarchargerp.kill()
			self.solarchargerp.wait()
		except (AttributeError, OSError):
			pass

	def stop_dbusgenerator_service(self):
		try:
			self.dbusgeneratorp.kill()
			self.dbusgeneratorp.wait()
		except (AttributeError, OSError):
			pass

	def stop_battery_service(self):
		try:
			self.batteryp.kill()
			self.batteryp.wait()
		except (AttributeError, OSError):
			pass

	def reset_all_conditons(self):
		self.set_condition("Soc", 0, 0, 0)
		self.set_condition_timed("BatteryCurrent", 0, 0, 0, 0, 0)
		self.set_condition_timed("BatteryVoltage", 0, 0, 0, 0, 0)
		self.set_condition_timed("AcLoad", 0, 0, 0, 0, 0)
		self.set_value(self._settingspath, '/Settings/Generator0/TestRun/Enabled', 0)
		self.set_value(self._settingspath, '/Settings/Generator0/QuietHours/Enabled', 0)
		self.set_value(self._settingspath, '/Settings/Generator0/MinimumRuntime', 0)
		self.set_value(self._generatorpath, '/ManualStart', 0)
		self.set_value(self._generatorpath, '/ManualStartTimer', 0)
		self.set_value(self._settingspath, '/Settings/Generator0/TestRun/RunTillBatteryFull', 0)
		self.set_value(self._settingspath, "/Settings/Generator0/AutoStartEnabled", 1)
		self.set_value(self._settingspath, '/Settings/Generator0/OnLossCommunication', 0)

		time.sleep(2)  # Make sure generator stops

	def fill_history(self):
		today = calendar.timegm(datetime.date.today().timetuple())
		history = dict()
		for i in range(30):
			date = today - (i * 86400)
			history[str(date)] = random.randint(1800, 3600)
		self.set_value(self._settingspath, '/Settings/Generator0/AccumulatedDaily', json.dumps(history, sort_keys=True))
		self.set_value(self._settingspath, '/Settings/Generator0/AccumulatedTotal', sum(history.values()))

	def test_timed_condition(self):
		# Make the condition timer start setting current value to start/stop value
		# then set current value off the condition start/stop value, it should reset the timer.

		startvalue = int(random.uniform(-30, -11))
		stopvalue = int(random.uniform(-10, -1))
		starttimer = random.randint(5, 10)
		stoptimer = random.randint(5, 10)

		self.set_value(self.batteryservice, '/Dc/0/Current', stopvalue + 1)

		# Start
		self.set_condition_timed("BatteryCurrent", -startvalue, -stopvalue, starttimer, stoptimer, 1)

		self.set_value(self.batteryservice, '/Dc/0/Current', startvalue)
		self.assertEqual(0, self.get_state(starttimer - 2))
		# Reset the timer
		self.set_value(self.batteryservice, '/Dc/0/Current', startvalue + 1)
		time.sleep(2)
		self.set_value(self.batteryservice, '/Dc/0/Current', startvalue)
		# If timer was correctly resetted, generator should still stopped
		self.assertEqual(0, self.get_state(starttimer - 2))
		# Finally generator should start
		self.assertEqual(1, self.get_state(5))

		# Stop
		self.set_value(self.batteryservice, '/Dc/0/Current', stopvalue)
		time.sleep(stoptimer - 2)
		self.set_value(self.batteryservice, '/Dc/0/Current', stopvalue - 1)
		time.sleep(1)
		self.set_value(self.batteryservice, '/Dc/0/Current', stopvalue)
		self.assertEqual(1, self.get_state(stoptimer - 1))
		self.assertEqual(0, self.get_state(5))

	def test_minimum_runtime(self):
		self.set_value(self._settingspath, '/Settings/Generator0/MinimumRuntime', 1)
		self.set_condition_timed("BatteryCurrent", 15, 10, 2, 2, 1)
		self.set_value(self.batteryservice, '/Dc/0/Current', -15)
		# Generator started
		self.assertEqual(1, self.get_state(5))
		# Set value to stop the generator
		self.set_value(self.batteryservice, '/Dc/0/Current', -10)
		# Generator still running due to minimum runtime
		self.assertEqual(1, self.get_state(50))
		# Minimum runtime met and generator stops
		self.assertEqual(0, self.get_state(10))

	def test_manualstart(self):
		self.set_value(self._generatorpath, '/ManualStart', 1)
		self.assertEqual(1, self.get_state(2))
		self.set_value(self._generatorpath, '/ManualStart', 0)
		self.assertEqual(0, self.get_state(2))

		# Timed
		randomtimer = random.randint(10, 20)
		self.set_value(self._generatorpath, '/ManualStartTimer', randomtimer)
		self.set_value(self._generatorpath, '/ManualStart', 1)
		self.assertEqual(1, self.get_state(1))
		self.assertEqual(0, self.get_state(randomtimer + 3))

	def test_testrun(self):
		# The random generated history is set to a maximum of one hour per day, setting the testrun
		# accumulated time to 10h and the interval to a maximum of 9 days makes sure that the maintenace
		# will not be skipped.

		today = calendar.timegm(datetime.date.today().timetuple())
		interval = random.randint(1, 9)
		setdate = today - (interval * 86400)
		currenttime = time.time() - time.mktime(datetime.date.today().timetuple())

		self.set_value(self._settingspath, '/Settings/Generator0/TestRun/RunTillBatteryFull', 0)
		self.set_value(self._settingspath, '/Settings/Generator0/TestRun/Enabled', 1)
		self.set_value(self._settingspath, '/Settings/Generator0/TestRun/SkipRuntime', 36000)
		self.set_value(self._settingspath, '/Settings/Generator0/TestRun/StartDate', setdate)
		self.set_value(self._settingspath, '/Settings/Generator0/TestRun/StartTime', currenttime)
		self.set_value(self._settingspath, '/Settings/Generator0/TestRun/Interval', interval)
		self.set_value(self._settingspath, '/Settings/Generator0/TestRun/Duration', 15)

		self.assertEqual(1, self.get_state(3))
		self.assertEqual(1, self.get_state(7))
		self.assertEqual(0, self.get_state(8))

		# Change the accumulated time to one hour, test run should be skipped
		self.set_value(self._settingspath, '/Settings/Generator0/TestRun/SkipRuntime', 3600)

		self.assertEqual(1, self.wait_and_get('/SkipTestRun', 2))
		self.assertEqual(0, self.get_state(0))

		# Check run till battery is full
		currenttime = time.time() - time.mktime(datetime.date.today().timetuple())
		self.set_value(self._settingspath, '/Settings/Generator0/TestRun/StartTime', currenttime)
		self.set_value(self.batteryservice, '/Soc', 80)
		self.set_value(self._settingspath, '/Settings/Generator0/TestRun/RunTillBatteryFull', 1)
		self.assertEqual(0, self.get_state(5))
		self.set_value(self._settingspath, '/Settings/Generator0/TestRun/SkipRuntime', 36000)
		self.assertEqual(1, self.get_state(5))

		# Remove battery, rerty mechanism must keep the generator
		# running
		self.stop_battery_service()
		self.assertEqual(1, self.get_state(self.retriesonerror / 2))
		self.start_services('battery')

		# The start window when run till battery full is 60 seconds
		# wait and make sure that still running
		self.assertEqual(1, self.get_state(65))

		# Test run should end when battery is full
		self.set_value(self.batteryservice, '/Soc', 100)
		self.assertEqual(0, self.get_state(5))

	def test_quiethours_mode(self):

		currenttime = time.time() - time.mktime(datetime.date.today().timetuple())
		self.set_value(self._settingspath, '/Settings/Generator0/QuietHours/StartTime', currenttime)
		self.set_value(self._settingspath, '/Settings/Generator0/QuietHours/EndTime', currenttime + 20)

		self.set_value(self.batteryservice, '/Dc/0/Current', -15)
		self.set_condition_timed("BatteryCurrent", 15, 10, 2, 2, 1)
		self.set_condition_timed("BatteryCurrent", 25, 15, 2, 2, 1, True)

		# Battery current condition must make generator start
		self.assertEqual(1, self.wait_and_get('/State', 5))
		self.set_value(self._settingspath, '/Settings/Generator0/QuietHours/Enabled', 1)

		# Entering to secondary time zone, generator must stop after stroptimer
		self.assertEqual(0, self.wait_and_get('/State', 5))

		# Timezone start value must make the generator start
		self.set_value(self.batteryservice, '/Dc/0/Current', -25)
		self.assertEqual(1, self.wait_and_get('/State', 5))

		# Wait till time zones ends, generator must continue running because current still above stop value
		self.assertEqual(1, self.wait_and_get('/State', 5))

		# Set current to stop value, generator must stop
		self.set_value(self.batteryservice, '/Dc/0/Current', -10)
		self.assertEqual(0, self.wait_and_get('/State', 5))

	def test_condition_cascade(self, emergency=False):
		# Generator must keep running till no condition is reached
		# Conditions order: Manual, Soc, AcLoad, BatteryCurrent, BatteryVoltage, Test run
		starttimer = 2
		stoptimer = 2

		currenttime = time.time() - time.mktime(datetime.date.today().timetuple())

		self.set_value(self.vebusservice, '/Ac/Out/L1/P', 24)
		self.set_value(self.batteryservice, '/Dc/0/Current', -25)
		self.set_value(self.batteryservice, '/Dc/0/Voltage', 23)

		self.set_condition("Soc", 80, 85, 1, emergency)
		self.set_condition_timed("AcLoad", 24, 23, starttimer, stoptimer, 1, emergency)
		self.set_condition_timed("BatteryCurrent", 15, 10, starttimer, stoptimer, 1, emergency)
		self.set_condition_timed("BatteryVoltage", 23, 24, starttimer, stoptimer, 1, emergency)
		self.set_value(self.batteryservice, '/Soc', 80)
		self.set_value(self._settingspath, '/Settings/Generator0/TestRun/SkipRuntime', 36000)
		self.set_value(self._settingspath, '/Settings/Generator0/TestRun/Interval', 1)
		self.set_value(self._settingspath, '/Settings/Generator0/TestRun/StartTime', currenttime)
		self.set_value(self._settingspath, '/Settings/Generator0/TestRun/Duration', 60)
		self.set_value(self._settingspath, '/Settings/Generator0/TestRun/Enabled', 1)

		self.set_value(self._generatorpath, '/ManualStart', 1)

		self.assertEqual('testrun', self.wait_and_get('/RunningByCondition', stoptimer + 2))
		self.set_value(self._settingspath, '/Settings/Generator0/TestRun/Enabled', 0)

		self.assertEqual('manual', self.wait_and_get('/RunningByCondition', stoptimer + 2))
		self.set_value(self._generatorpath, '/ManualStart', 0)

		self.assertEqual('soc', self.wait_and_get('/RunningByCondition', stoptimer + 2))
		self.set_value(self.batteryservice, '/Soc', 85)

		self.assertEqual('acload', self.wait_and_get('/RunningByCondition', stoptimer + 2))
		self.set_value(self.vebusservice, '/Ac/Out/L1/P', 1)

		self.assertEqual('batterycurrent', self.wait_and_get('/RunningByCondition', stoptimer + 2))
		self.set_value(self.batteryservice, '/Dc/0/Current', -10)

		self.assertEqual('batteryvoltage', self.wait_and_get('/RunningByCondition', stoptimer + 2))
		self.set_value(self.batteryservice, '/Dc/0/Voltage', 24)

		self.assertGreaterEqual(self.get_value(self._generatorpath, '/Runtime'), 11)

		self.assertEqual(0,  self.get_state(stoptimer + 2))

	def test_remove_battery_service(self):
		self.set_value(self.batteryservice, '/Dc/0/Current', -15)
		self.set_condition_timed("BatteryCurrent", 14, 10, 0, 0, 1)
		self.assertEqual(1, self.get_state(5))
		self.stop_battery_service()
		# Retry connection mecanism must keep the generator running
		# for 5 minutres
		self.assertEqual(1, self.get_state(self.retriesonerror / 2))
		self.assertEqual(0, self.get_state(self.retriesonerror / 2 + 10))
		self.start_services('battery')
		self.set_value(self.batteryservice, '/Dc/0/Current', -15)
		self.assertEqual(1, self.get_state(10))

	def test_remove_battery_service_keeprunning(self):
		self.set_value(self._settingspath, '/Settings/Generator0/OnLossCommunication', 2)
		self.set_value(self.batteryservice, '/Dc/0/Current', -15)
		self.set_condition_timed("BatteryCurrent", 14, 10, 0, 0, 1)
		self.assertEqual(1, self.get_state(5))
		self.stop_battery_service()
		# Retry connection mecanism must keep the generator running
		# for 5 minutres
		self.assertEqual(1, self.get_state(self.retriesonerror / 2))
		self.assertEqual(1, self.get_state(self.retriesonerror / 2 + 10))
		self.assertEqual('lossofcommunication', self.wait_and_get('/RunningByCondition', 1))
		self.start_services('battery')
		self.set_value(self.batteryservice, '/Dc/0/Current', -15)
		self.assertEqual(1, self.get_state(10))
		self.assertEqual('batterycurrent', self.wait_and_get('/RunningByCondition', 1))

	def test_remove_vebus_service(self):
		self.set_value(self._settingspath, '/Settings/Generator0/OnLossCommunication', 0)
		self.stop_vebus_service()
		self.start_services('vebus')
		time.sleep(5)
		self.set_value(self.vebusservice, '/Ac/Out/L1/P', 15)
		self.set_condition_timed("AcLoad", 14, 10, 0, 5, 1)
		self.assertEqual(1, self.get_state(5))
		self.stop_vebus_service()
		# Retry connection mecanism must keep the generator running
		# for 'retriesonerror' seconds
		self.assertEqual(1, self.get_state(self.retriesonerror / 2))
		self.assertEqual(0, self.get_state(self.retriesonerror / 2 + 10))
		self.start_services('vebus')
		self.set_value(self.vebusservice, '/Ac/Out/L1/P', 15)
		self.assertEqual(1, self.get_state(7))

	def test_autostart_oncomfailure(self):
		self.stop_vebus_service()
		self.start_services('vebus')
		# Enable acload condition otherwise communications are not checked
		self.set_condition_timed("AcLoad", 140, 10, 1500, 0, 1)
		self.set_value(self.vebusservice, '/Ac/Out/L1/P', 15)
		self.set_value(self._settingspath, '/Settings/Generator0/OnLossCommunication', 1)
		self.stop_vebus_service()
		self.assertEqual(1, self.get_state(self.retriesonerror + 10))
		self.start_services('vebus')

	def test_keeprunning_oncomfailure(self):
		self.set_value(self._settingspath, '/Settings/Generator0/OnLossCommunication', 2)

		self.stop_vebus_service()
		# Generator not running must expect the same after connection lost
		self.assertEqual(0, self.get_state(self.retriesonerror + 5))

		self.start_services('vebus')
		time.sleep(5)
		self.set_value(self.vebusservice, '/Ac/Out/L1/P', 15)
		self.set_condition_timed("AcLoad", 14, 10, 0, 5, 1)
		self.assertEqual(1, self.get_state(5))
		self.stop_vebus_service()
		# Generator is running and should keep running after communications error
		self.assertEqual(1, self.get_state(self.retriesonerror / 2))
		self.assertEqual(1, self.get_state(self.retriesonerror / 2 + 5))
		self.assertEqual('lossofcommunication', self.wait_and_get('/RunningByCondition', 1))
		self.start_services('vebus')
		self.set_value(self.vebusservice, '/Ac/Out/L1/P', 15)
		self.assertEqual(1, self.get_state(1))
		self.assertEqual('acload', self.wait_and_get('/RunningByCondition', 1))
		self.set_value(self.vebusservice, '/Ac/Out/L1/P', 0)
		self.assertEqual(0, self.get_state(10))

	def test_disable_autostart(self):
		self.set_condition("Soc", 80, 85, 1)
		self.set_value(self.batteryservice, '/Soc', 80)
		self.assertEqual(1, self.get_state(5))
		self.set_value(self._settingspath, "/Settings/Generator0/AutoStartEnabled", 0)
		self.assertEqual(0, self.get_state(5))
		# When autostart is off the generator manual start should continue working
		self.set_value(self._generatorpath, '/ManualStart', 1)
		self.assertEqual(1, self.get_state(5))

	def test_go_off(self):
		self.stop_vebus_service()
		self.start_services('vebus')
		time.sleep(5)
		self.set_value(self.vebusservice, '/Ac/Out/L1/P', 16)
		self.set_condition_timed("AcLoad", 14, 10, 16, 5, 1)
		self.assertEqual(1, self.get_state(20))
		# Set relay function to alarm relay
		self.set_value(self._settingspath, "/Settings/Relay/Function", 0)
		time.sleep(5)
		# Set relay funtion to generator start/stop
		self.set_value(self._settingspath, "/Settings/Relay/Function", 1)
		# When the service go off all timers are reset, at this point generator
		# must be stopped. Times/delaus are long because differences between
		# PC and CCGX startup times, setting long times we make sure the test will
		# work on both plattforms.
		self.assertEqual(0, self.get_state(15))
		# Timer finished, generator must be started
		self.assertEqual(1, self.get_state(20))

	def wait_and_get(self, setting, delay):
		time.sleep(delay)
		return self.get_value(self._generatorpath, setting)

	def get_state(self, delay):
		state = self.wait_and_get('/State', delay)

		return state

	def set_condition_timed(self, condition, start, stop, startimer, stoptimer, enabled, emergency=False, *arglist):
		settings = ({"StartValue": start, "StopValue": stop, "StartTimer": startimer,
					 "StopTimer": stoptimer, "Enabled": enabled})
		if emergency:
			settings["QuietHoursStartValue"] = settings.pop("StartValue")
			settings["QuietHoursStopValue"] = settings.pop("StopValue")
		for s, v in settings.iteritems():
			self.set_value(self._settingspath, "/Settings/Generator0/" + condition + "/" + s, v)

	def set_condition(self, condition, start, stop, enabled, emergency=False):
		settings = ({"StartValue": start, "StopValue": stop, "Enabled": enabled})
		if emergency:
			settings["QuietHoursStartValue"] = settings.pop("StartValue")
			settings["QuietHoursStopValue"] = settings.pop("StopValue")
		for s, v in settings.iteritems():
			self.set_value(self._settingspath, "/Settings/Generator0/" + condition + "/" + s, v)

	def set_value(self, path, setting, value):
		dbusobject = dbus.Interface(self.bus.get_object(path, setting), None)
		dbusobject.SetValue(value)

	def get_value(self, path, setting):
		dbusobject = dbus.Interface(self.bus.get_object(path, setting), None)
		return dbusobject.GetValue()

if __name__ == '__main__':
	DBusGMainLoop(set_as_default=True)
	unittest.main(exit=True)
