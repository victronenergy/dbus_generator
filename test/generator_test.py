#!/usr/bin/env python
import json
import os
import sys
import unittest
from time import sleep
import datetime
import calendar

# our own packages
test_dir = os.path.dirname(__file__)
sys.path.insert(0, test_dir)
sys.path.insert(1, os.path.join(test_dir, '..', 'ext', 'velib_python', 'test'))
sys.path.insert(1, os.path.join(test_dir, '..'))
import dbus_generator
import gobject
from logger import setup_logging
from mock_dbus_monitor import MockDbusMonitor
from mock_dbus_service import MockDbusService
from mock_settings_device import MockSettingsDevice

dbus_generator.logger = setup_logging()


class MockGenerator(dbus_generator.Generator):
	def _create_dbus_monitor(self, *args, **kwargs):
		return MockDbusMonitor(*args, **kwargs)

	def _create_settings(self, *args, **kwargs):
		return MockSettingsDevice(*args, **kwargs)

	def _create_dbus_service(self):
		return MockDbusService('com.victronenergy.generator.startstop0')


class TestGeneratorBase(unittest.TestCase):
	def __init__(self, methodName='runTest'):
		unittest.TestCase.__init__(self, methodName)

	def setUp(self):
		gobject.timer_manager.reset()
		self._generator_ = MockGenerator()
		self._monitor = self._generator_._dbusmonitor

	def _update_values(self, interval=1000):
		if not self._service:
			self._service = self._generator_._dbusservice
		gobject.timer_manager.add_terminator(interval)
		gobject.timer_manager.start()

	def _add_device(self, service, values, connected=True, product_name='dummy', connection='dummy', instance=0):
		values['/Connected'] = 1 if connected else 0
		values['/ProductName'] = product_name
		values['/Mgmt/Connection'] = connection
		values.setdefault('/DeviceInstance', instance)
		self._monitor.add_service(service, values)

	def _remove_device(self, service):
		self._monitor.remove_service(service)

	def _set_setting(self, path, value):
		self._generator_._settings[self._generator_._settings.get_short_name(path)] = value

	def _today(self):
		now = datetime.datetime.now()
		midnight = datetime.datetime.combine(now.date(), datetime.time(0))
		return calendar.timegm(midnight.timetuple())

	def _seconds_since_midnight(self):
		now = datetime.datetime.now()
		midnight = datetime.datetime.combine(now.date(), datetime.time(0))
		delta = now - midnight
		return delta.total_seconds()

	def _yesterday(self):
		now = datetime.datetime.now()
		midnight = datetime.datetime.combine(now.date(), datetime.time(0))
		yesterday = midnight - datetime.timedelta(days=1)
		return calendar.timegm(yesterday.timetuple())

	def _check_values(self, values):
		ok = True
		for k,v in values.items():
			v2 = self._service[k] if k in self._service else None
			if isinstance(v, (int, float)) and v2 is not None:
				d = abs(v - v2)
				if d > 1e-6:
					ok = False
					break
			else:
				if v != v2:
					ok = False
					break
		if ok:
			return
		msg = ''
		for k,v in values.items():
			msg += '{0}:\t{1}'.format(k, v)
			if k in self._service:
				msg += '\t{}'.format(self._service[k])
			msg += '\n'
		self.assertTrue(ok, msg)


class TestGenerator(TestGeneratorBase):
	def __init__(self, methodName='runTest'):
		TestGeneratorBase.__init__(self, methodName)

	def setUp(self):
		TestGeneratorBase.setUp(self)
		self._add_device('com.victronenergy.system',
			product_name='SystemCalc',
			values={
				'/Ac/Consumption/L1/Power': 650,
				'/Ac/Consumption/L2/Power': 650,
				'/Ac/Consumption/L3/Power': 650,
				'/Ac/PvOnOutput/L1/Power': 150,
				'/Ac/PvOnOutput/L2/Power': 150,
				'/Ac/PvOnOutput/L3/Power': 150,
				'/Ac/PvOnGrid/L1/Power': 150,
				'/Ac/PvOnGrid/L2/Power': 150,
				'/Ac/PvOnGrid/L3/Power': 150,
				'/Ac/PvOnGenset/L1/Power': 0,
				'/Ac/PvOnGenset/L2/Power': 0,
				'/Ac/PvOnGenset/L3/Power': 0,
				'/Ac/PvOnGenset/Total/Power': 0,
				'/Dc/Pv/Power': 0,
				'/AutoSelectedBatteryMeasurement': "com_victronenergy_battery_258/Dc/0",
				'/VebusService': "com.victronenergy.vebus.ttyO1",
				'/Relay/0/State': 0
				})

		self._add_device('com.victronenergy.vebus.ttyO1',
			product_name='Multi',
			instance=251,
			values={
				'/Dc/0/Voltage': 14.4,
				'/Dc/0/Current': 10,
				'/Alarms/Overload': None,
				'/Alarms/HighTemperature': None,
				'/Alarms/L1/Overload': 0,
				'/Alarms/L2/Overload': 0,
				'/Alarms/L3/Overload': 0,
				'/Alarms/L1/HighTemperature': 0,
				'/Alarms/L2/HighTemperature': 0,
				'/Alarms/L3/HighTemperature': 0,
				'/Ac/Out/L1/P': 500,
				'/Ac/Out/L2/P': 500,
				'/Ac/Out/L3/P': 500,
				'/Ac/Out/P': 1500,
				'/Ac/ActiveIn/ActiveInput': 1,
				'/Ac/ActiveIn/Connected': 0,
				'/Soc': 87
				})

		self._add_device('com.victronenergy.battery.ttyO5',
			product_name='battery',
			instance=258,
			values={
				'/Dc/0/Voltage': 14.4,
				'/Dc/0/Current': 10,
				'/Soc': 87
				})

		self._add_device('com.victronenergy.settings',
			values={
				'/Settings/Relay/Function': 1,
				'/Settings/System/TimeZone': 'Europe/Berlin'
			})
		# DBus service is not created till Settings/Relay/Function is 1
		self._service = self._generator_._dbusservice

	def test_acload_consumption(self):
		self._monitor.set_value('com.victronenergy.system', '/Ac/Consumption/L1/Power', 1900)
		self._monitor.set_value('com.victronenergy.system', '/Ac/Consumption/L2/Power', 100)
		self._monitor.set_value('com.victronenergy.system', '/Ac/Consumption/L3/Power', 600)
		
		self._set_setting('/Settings/Generator0/AcLoad/Enabled', 1)
		self._set_setting('/Settings/Generator0/AcLoad/Measurement', 0)
		self._set_setting('/Settings/Generator0/AcLoad/StartValue', 2600)
		self._set_setting('/Settings/Generator0/AcLoad/StopValue', 800)
		self._set_setting('/Settings/Generator0/AcLoad/StartTimer', 0)
		self._set_setting('/Settings/Generator0/AcLoad/StopTimer', 0)

		self._update_values()
		self._check_values({
			'/State': 1
		})

	def test_activeinput(self):
		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Ac/Out/L1/P', 700)
		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Ac/Out/L2/P', 700)
		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Ac/Out/L3/P', 700)
		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Ac/Out/P', 2100)
		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Ac/ActiveIn/Connected', 1)
		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Ac/ActiveIn/ActiveInput', 1)
		self._set_setting('/Settings/Generator0/AcLoad/Enabled', 1)
		self._set_setting('/Settings/Generator0/AcLoad/Measurement', 1)
		self._set_setting('/Settings/Generator0/AcLoad/StartValue', 1650)
		self._set_setting('/Settings/Generator0/AcLoad/StopValue', 800)
		self._set_setting('/Settings/Generator0/AcLoad/StartTimer', 0)
		self._set_setting('/Settings/Generator0/AcLoad/StopTimer', 0)
		self._set_setting('/Settings/Generator0/StopWhenAc1Available', 1)

		self._update_values()
		self._check_values({
			'/State': 1
		})
		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Ac/ActiveIn/ActiveInput', 0)
		self._update_values()
		self._check_values({
			'/State': 0
		})
		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Ac/ActiveIn/Connected', 0)
		self._update_values()
		self._check_values({
			'/State': 1
		})
		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Ac/ActiveIn/Connected', 1)
		self._update_values()
		self._check_values({
			'/State': 0
		})
		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Ac/Out/P', 500)
		self._update_values()
		self._check_values({
			'/State': 0
		})

	def test_acload(self):
		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Ac/Out/L1/P', 700)
		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Ac/Out/L2/P', 700)
		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Ac/Out/L3/P', 700)
		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Ac/Out/P', 2100)
		self._set_setting('/Settings/Generator0/AcLoad/Enabled', 1)
		self._set_setting('/Settings/Generator0/AcLoad/Measurement', 1)
		self._set_setting('/Settings/Generator0/AcLoad/StartValue', 2200)
		self._set_setting('/Settings/Generator0/AcLoad/StopValue', 800)
		self._set_setting('/Settings/Generator0/AcLoad/StartTimer', 0)
		self._set_setting('/Settings/Generator0/AcLoad/StopTimer', 0)

		self._update_values()
		self._check_values({
			'/State': 0
		})
		self._set_setting('/Settings/Generator0/AcLoad/StartValue', 1650)
		self._update_values()
		self._check_values({
			'/State': 1
		})

	def test_overload_alarm_vebus(self):
		self._set_setting('/Settings/Generator0/InverterOverload/Enabled', 1)
		self._set_setting('/Settings/Generator0/InverterOverload/StartTimer', 0)
		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Alarms/L3/Overload', 1)

		self._update_values()
		self._check_values({
			'/State': 1,
			'/RunningByCondition': 'inverteroverload'
		})

	def test_hightemp_alarm_vebus(self):
		self._set_setting('/Settings/Generator0/InverterHighTemp/Enabled', 1)
		self._set_setting('/Settings/Generator0/InverterHighTemp/StartTimer', 0)
		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Alarms/L1/HighTemperature', 1)

		self._update_values()
		self._check_values({
			'/State': 1,
			'/RunningByCondition': 'inverterhightemp'
		})

	def test_hightemp_alarm_canbus(self):
		self._set_setting('/Settings/Generator0/InverterHighTemp/Enabled', 1)
		self._set_setting('/Settings/Generator0/InverterHighTemp/StartTimer', 0)
		# Multi connected to CAN-bus, doesn't have per-phase alarm paths, invalidate.
		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Alarms/L1/HighTemperature', None)
		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Alarms/L2/HighTemperature', None)
		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Alarms/L3/HighTemperature', None)
		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Alarms/HighTemperature', 1)

		self._update_values()
		self._check_values({
			'/State': 1,
			'/RunningByCondition': 'inverterhightemp'
		})

	def test_overload_alarm_canbus(self):
		self._set_setting('/Settings/Generator0/InverterOverload/Enabled', 1)
		self._set_setting('/Settings/Generator0/InverterOverload/StartTimer', 0)
		# Multi connected to CAN-bus, doesn't have per-phase alarm paths, invalidate.
		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Alarms/L1/Overload', None)
		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Alarms/L2/Overload', None)
		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Alarms/L3/Overload', None)
		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Alarms/Overload', 1)

		self._update_values()
		self._check_values({
			'/State': 1,
			'/RunningByCondition': 'inverteroverload'
		})

	def test_ac_highest_phase(self):
		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Ac/Out/L1/P', 550)
		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Ac/Out/L2/P', 660)
		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Ac/Out/L3/P', 500)
		self._update_values()
		self._set_setting('/Settings/Generator0/AcLoad/Enabled', 1)
		self._set_setting('/Settings/Generator0/AcLoad/Measurement', 2)
		self._set_setting('/Settings/Generator0/AcLoad/StartValue', 520)
		self._set_setting('/Settings/Generator0/AcLoad/StopValue', 500)
		self._set_setting('/Settings/Generator0/AcLoad/StartTimer', 0)
		self._set_setting('/Settings/Generator0/AcLoad/StopTimer', 0)

		self._update_values()
		self._check_values({
			'/State': 1
		})

	def test_manual_start(self):
		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Ac/ActiveIn/Connected', 1)
		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Ac/ActiveIn/ActiveInput', 1)
		self._set_setting('/Settings/Generator0/StopWhenAc1Available', 1)

		self._service['/ManualStart'] = 1
		self._update_values()
		self._check_values({
			'/State': 1
		})
		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Ac/ActiveIn/ActiveInput', 0)
		self._update_values()
		self._check_values({
			'/State': 1
		})
		self._service['/ManualStart'] = 0
		self._update_values()
		self._check_values({
			'/State': 0
		})

	def test_testrun(self):
		self._set_setting('/Settings/Generator0/TestRun/Enabled', 1)
		self._set_setting('/Settings/Generator0/TestRun/StartDate', self._yesterday())
		self._set_setting('/Settings/Generator0/TestRun/StartTime', self._seconds_since_midnight())
		self._set_setting('/Settings/Generator0/TestRun/Interval', 2)
		self._set_setting('/Settings/Generator0/TestRun/Duration', 2)
		self._set_setting('/Settings/Generator0/TestRun/SkipRuntime', 0)
		self._set_setting('/Settings/Generator0/TestRun/RunTillBatteryFull', 0)
		self._set_setting('/Settings/Generator0/StopWhenAc1Available', 1)

		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Ac/ActiveIn/Connected', 1)
		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Ac/ActiveIn/ActiveInput', 1)

		self._update_values()
		self._check_values({
			'/State': 0,
		})

		self._set_setting('/Settings/Generator0/TestRun/Interval', 1)
		self._update_values()
		self._check_values({
			'/State': 1,
		})

		sleep(1)
		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Ac/ActiveIn/ActiveInput', 0)
		self._update_values()
		self._check_values({
			'/State': 1
		})

		sleep(1)
		self._update_values()
		self._check_values({
			'/State': 0,
		})

	def test_skip_testrun(self):
		self._set_setting('/Settings/Generator0/TestRun/Enabled', 1)
		self._set_setting('/Settings/Generator0/TestRun/StartDate', self._today())
		self._set_setting('/Settings/Generator0/TestRun/StartTime', self._seconds_since_midnight())
		self._set_setting('/Settings/Generator0/TestRun/Interval', 4)
		self._set_setting('/Settings/Generator0/TestRun/Duration', 10)
		self._set_setting('/Settings/Generator0/TestRun/SkipRuntime', 1)
		self._set_setting('/Settings/Generator0/TestRun/RunTillBatteryFull', 0)

		daily = {
		str(int(self._today())): 600,
		str(int(self._yesterday())): 3000
		}

		self._set_setting('/Settings/Generator0/AccumulatedDaily', str(json.dumps(daily)))
		self._update_values()

		self._update_values()
		self._check_values({
			'/State': 0
		})

	def test_testrun_battery_full(self):
		self._set_setting('/Settings/Generator0/TestRun/Enabled', 1)
		self._set_setting('/Settings/Generator0/TestRun/StartDate', self._yesterday())
		self._set_setting('/Settings/Generator0/TestRun/StartTime', self._seconds_since_midnight())
		self._set_setting('/Settings/Generator0/TestRun/Interval', 1)
		self._set_setting('/Settings/Generator0/TestRun/Duration', 0)
		self._set_setting('/Settings/Generator0/TestRun/SkipRuntime', 3600)
		self._set_setting('/Settings/Generator0/TestRun/RunTillBatteryFull', 1)
		self._monitor.set_value('com.victronenergy.battery.ttyO5', '/Soc', 100)

		self._update_values()
		self._check_values({
			'/State': 0,
		})

		self._monitor.set_value('com.victronenergy.battery.ttyO5', '/Soc', 70)
		self._update_values()
		self._check_values({
			'/State': 1,
		})

		self._monitor.set_value('com.victronenergy.battery.ttyO5', '/Soc', 100)
		self._update_values()
		self._check_values({
			'/State': 0,
		})

	def test_comm_failure(self):
		self._monitor.set_value('com.victronenergy.system', '/Ac/Consumption/L1/Power', 1900)
		self._monitor.set_value('com.victronenergy.system', '/Ac/Consumption/L2/Power', 100)
		self._monitor.set_value('com.victronenergy.system', '/Ac/Consumption/L3/Power', 600)
		self._set_setting('/Settings/Generator0/AcLoad/Enabled', 1)
		self._set_setting('/Settings/Generator0/AcLoad/Measurement', 0)
		self._set_setting('/Settings/Generator0/AcLoad/StartValue', 1600)
		self._set_setting('/Settings/Generator0/AcLoad/StopValue', 800)
		self._set_setting('/Settings/Generator0/AcLoad/StartTimer', 0)
		self._set_setting('/Settings/Generator0/AcLoad/StopTimer', 0)

		self._update_values()
		self._check_values({
			'/State': 1
		})

		self._remove_device("com.victronenergy.vebus.ttyO1")
		self._monitor.set_value('com.victronenergy.system', '/VebusService', [])

		for x in range(0, 300):
			self._check_values({
				'/State': 1
			})
			self._update_values()

		self._update_values()
		self._check_values({
			'/State': 0
		})

	def test_comm_failure_continue_running(self):
		self._monitor.set_value('com.victronenergy.system', '/Ac/Consumption/L1/Power', 1900)
		self._monitor.set_value('com.victronenergy.system', '/Ac/Consumption/L2/Power', 100)
		self._monitor.set_value('com.victronenergy.system', '/Ac/Consumption/L3/Power', 600)
		self._set_setting('/Settings/Generator0/OnLossCommunication', 2)
		self._set_setting('/Settings/Generator0/AcLoad/Enabled', 1)
		self._set_setting('/Settings/Generator0/AcLoad/Measurement', 0)
		self._set_setting('/Settings/Generator0/AcLoad/StartValue', 1600)
		self._set_setting('/Settings/Generator0/AcLoad/StopValue', 800)
		self._set_setting('/Settings/Generator0/AcLoad/StartTimer', 0)
		self._set_setting('/Settings/Generator0/AcLoad/StopTimer', 0)

		self._update_values()
		self._check_values({
			'/State': 1
		})
		self._remove_device("com.victronenergy.vebus.ttyO1")
		self._monitor.set_value('com.victronenergy.system', '/VebusService', [])

		for x in range(0, 300):
			self._check_values({
				'/State': 1
			})
			self._update_values()

		self._update_values()
		self._check_values({
			'/State': 1
		})

	def test_comm_failure_start(self):
		self._monitor.set_value('com.victronenergy.system', '/Ac/Consumption/L1/Power', 50)
		self._monitor.set_value('com.victronenergy.system', '/Ac/Consumption/L2/Power', 25)
		self._monitor.set_value('com.victronenergy.system', '/Ac/Consumption/L3/Power', 25)
		self._set_setting('/Settings/Generator0/OnLossCommunication', 1)
		self._set_setting('/Settings/Generator0/AcLoad/Enabled', 1)
		self._set_setting('/Settings/Generator0/AcLoad/Measurement', 0)
		self._set_setting('/Settings/Generator0/AcLoad/StartValue', 1600)
		self._set_setting('/Settings/Generator0/AcLoad/StopValue', 800)
		self._set_setting('/Settings/Generator0/AcLoad/StartTimer', 0)
		self._set_setting('/Settings/Generator0/AcLoad/StopTimer', 0)

		self._remove_device("com.victronenergy.vebus.ttyO1")
		self._monitor.set_value('com.victronenergy.system', '/VebusService', [])

		for x in range(0, 300):
			self._check_values({
				'/State': 0
			})
			self._update_values()

		self._update_values()
		self._check_values({
			'/State': 1
		})

	def test_comm_failure_battery(self):
		self._set_setting('/Settings/Generator0/OnLossCommunication', 0)
		self._set_setting('/Settings/Generator0/BatteryCurrent/Enabled', 1)
		self._set_setting('/Settings/Generator0/BatteryCurrent/StartValue', 60)
		self._set_setting('/Settings/Generator0/BatteryCurrent/StopValue', 30)
		self._set_setting('/Settings/Generator0/BatteryCurrent/StartTimer', 0)
		self._set_setting('/Settings/Generator0/BatteryCurrent/StopTimer', 0)
		self._monitor.set_value('com.victronenergy.battery.ttyO5', '/Dc/0/Current', -60)

		self._update_values()
		self._check_values({
			'/State': 1
		})

		self._monitor.set_value('com.victronenergy.system', '/AutoSelectedBatteryMeasurement', [])
		self._remove_device("com.victronenergy.battery.ttyO5")
		for x in range(0, 300):
			self._check_values({
				'/State': 1
			})
			self._update_values()


		self._update_values()
		self._check_values({
			'/State': 0
		})

	def test_comm_failure_battery_continue_running(self):
		self._set_setting('/Settings/Generator0/OnLossCommunication', 2)
		self._set_setting('/Settings/Generator0/BatteryCurrent/Enabled', 1)
		self._set_setting('/Settings/Generator0/BatteryCurrent/StartValue', 60)
		self._set_setting('/Settings/Generator0/BatteryCurrent/StopValue', 30)
		self._set_setting('/Settings/Generator0/BatteryCurrent/StartTimer', 0)
		self._set_setting('/Settings/Generator0/BatteryCurrent/StopTimer', 0)
		self._monitor.set_value('com.victronenergy.battery.ttyO5', '/Dc/0/Current', -60)

		self._update_values()
		self._check_values({
			'/State': 1
		})

		self._monitor.set_value('com.victronenergy.system', '/AutoSelectedBatteryMeasurement', [])
		self._remove_device("com.victronenergy.battery.ttyO5")

		for x in range(0, 300):
			self._check_values({
				'/State': 1
			})
			self._update_values()

		self._update_values()
		self._check_values({
			'/State': 1
		})

	def test_comm_failure_battery_start(self):
		self._set_setting('/Settings/Generator0/OnLossCommunication', 1)
		self._set_setting('/Settings/Generator0/BatteryCurrent/Enabled', 1)
		self._set_setting('/Settings/Generator0/BatteryCurrent/StartValue', 60)
		self._set_setting('/Settings/Generator0/BatteryCurrent/StopValue', 30)
		self._set_setting('/Settings/Generator0/BatteryCurrent/StartTimer', 0)
		self._set_setting('/Settings/Generator0/BatteryCurrent/StopTimer', 0)
		self._monitor.set_value('com.victronenergy.battery.ttyO5', '/Dc/0/Current', 0)

		self._update_values()
		self._check_values({
			'/State': 0
		})

		self._monitor.set_value('com.victronenergy.system', '/AutoSelectedBatteryMeasurement', [])
		self._remove_device("com.victronenergy.battery.ttyO5")

		for x in range(0, 300):
			self._check_values({
				'/State': 0
			})
			self._update_values()

		self._update_values()
		self._check_values({
			'/State': 1
		})

	def test_disable_autostart(self):
		self._set_setting('/Settings/Generator0/BatteryCurrent/Enabled', 1)
		self._set_setting('/Settings/Generator0/BatteryCurrent/StartValue', 60)
		self._set_setting('/Settings/Generator0/BatteryCurrent/StopValue', 30)
		self._set_setting('/Settings/Generator0/BatteryCurrent/StartTimer', 0)
		self._set_setting('/Settings/Generator0/BatteryCurrent/StopTimer', 0)
		self._monitor.set_value('com.victronenergy.battery.ttyO5', '/Dc/0/Current', -60)

		self._update_values()
		self._check_values({
			'/State': 1
		})
		self._set_setting('/Settings/Generator0/AutoStartEnabled', 0)
		self._update_values()
		self._check_values({
			'/State': 0
		})

	def test_disable_autostart_manual(self):
		self._set_setting('/Settings/Generator0/AutoStartEnabled', 0)
		self._service['/ManualStart'] = 1
		self._update_values()
		self._check_values({
			'/State': 1
		})

	def test_minimum_runtime(self):
		self._set_setting('/Settings/Generator0/MinimumRuntime', 0.010)  # Minutes
		self._set_setting('/Settings/Generator0/BatteryCurrent/Enabled', 1)
		self._set_setting('/Settings/Generator0/BatteryCurrent/StartValue', 60)
		self._set_setting('/Settings/Generator0/BatteryCurrent/StopValue', 30)
		self._set_setting('/Settings/Generator0/BatteryCurrent/StartTimer', 0)
		self._set_setting('/Settings/Generator0/BatteryCurrent/StopTimer', 0)
		self._monitor.set_value('com.victronenergy.battery.ttyO5', '/Dc/0/Current', -60)

		self._update_values()
		self._check_values({
			'/State': 1
		})

		self._monitor.set_value('com.victronenergy.battery.ttyO5', '/Dc/0/Current', 0)
		self._update_values()
		self._check_values({
			'/State': 1
		})

		sleep(1)
		self._update_values()
		self._check_values({
			'/State': 0
		})

	def test_timed_condition(self):
		self._set_setting('/Settings/Generator0/MinimumRuntime', 0.010)  # Minutes
		self._set_setting('/Settings/Generator0/BatteryCurrent/Enabled', 1)
		self._set_setting('/Settings/Generator0/BatteryCurrent/StartValue', 60)
		self._set_setting('/Settings/Generator0/BatteryCurrent/StopValue', 30)
		self._set_setting('/Settings/Generator0/BatteryCurrent/StartTimer', 1)
		self._set_setting('/Settings/Generator0/BatteryCurrent/StopTimer', 1)
		self._monitor.set_value('com.victronenergy.battery.ttyO5', '/Dc/0/Current', -60)

		self._update_values()
		self._check_values({
			'/State': 0
		})

		sleep(1)

		self._update_values()
		self._check_values({
			'/State': 1
		})

		self._monitor.set_value('com.victronenergy.battery.ttyO5', '/Dc/0/Current', 0)

		self._update_values()
		self._check_values({
			'/State': 1
		})

		sleep(1)
		self._update_values()
		self._check_values({
			'/State': 0
		})

	def test_quiethours(self):
		self._set_setting('/Settings/Generator0/BatteryCurrent/Enabled', 1)
		self._set_setting('/Settings/Generator0/BatteryCurrent/StartValue', 60)
		self._set_setting('/Settings/Generator0/BatteryCurrent/StopValue', 30)
		self._set_setting('/Settings/Generator0/BatteryCurrent/QuietHoursStartValue', 90)
		self._set_setting('/Settings/Generator0/BatteryCurrent/QuietHoursStopValue', 70)
		self._set_setting('/Settings/Generator0/BatteryCurrent/StartTimer', 0)
		self._set_setting('/Settings/Generator0/BatteryCurrent/StopTimer', 0)
		self._set_setting('/Settings/Generator0/QuietHours/Enabled', 1)
		self._set_setting('/Settings/Generator0/QuietHours/StartTime', self._seconds_since_midnight() + 1)
		self._set_setting('/Settings/Generator0/QuietHours/EndTime', self._seconds_since_midnight() + 2)

		self._monitor.set_value('com.victronenergy.battery.ttyO5', '/Dc/0/Current', -60)

		self._update_values()
		self._check_values({
			'/State': 1
		})
		self._set_setting('/Settings/Generator0/QuietHours/StartTime', self._seconds_since_midnight())
		self._update_values()
		self._check_values({
			'/State': 0
		})
		self._set_setting('/Settings/Generator0/QuietHours/StartTime', self._seconds_since_midnight() - 1)
		self._set_setting('/Settings/Generator0/QuietHours/EndTime', self._seconds_since_midnight())
		self._update_values()
		self._check_values({
			'/State': 1
		})

	def test_condition_cascade(self):
		self._set_setting('/Settings/Generator0/AcLoad/Enabled', 1)
		self._set_setting('/Settings/Generator0/AcLoad/Measurement', 1)
		self._set_setting('/Settings/Generator0/AcLoad/StartValue', 1100)
		self._set_setting('/Settings/Generator0/AcLoad/StopValue', 600)
		self._set_setting('/Settings/Generator0/AcLoad/StartTimer', 0)
		self._set_setting('/Settings/Generator0/AcLoad/StopTimer', 0)

		self._set_setting('/Settings/Generator0/Soc/Enabled', 1)
		self._set_setting('/Settings/Generator0/Soc/StartValue', 60)
		self._set_setting('/Settings/Generator0/Soc/StopValue', 70)

		self._set_setting('/Settings/Generator0/BatteryVoltage/Enabled', 1)
		self._set_setting('/Settings/Generator0/BatteryVoltage/StartValue', 11.5)
		self._set_setting('/Settings/Generator0/BatteryVoltage/StopValue', 13.7)
		self._set_setting('/Settings/Generator0/BatteryVoltage/StartTimer', 0)
		self._set_setting('/Settings/Generator0/BatteryVoltage/StopTimer', 0)

		self._set_setting('/Settings/Generator0/BatteryCurrent/Enabled', 1)
		self._set_setting('/Settings/Generator0/BatteryCurrent/StartValue', 60)
		self._set_setting('/Settings/Generator0/BatteryCurrent/StopValue', 30)
		self._set_setting('/Settings/Generator0/BatteryCurrent/StartTimer', 0)
		self._set_setting('/Settings/Generator0/BatteryCurrent/StopTimer', 0)

		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Ac/Out/L1/P', 600)
		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Ac/Out/L2/P', 850)
		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Ac/Out/L3/P', 550)
		self._monitor.set_value('com.victronenergy.battery.ttyO5', '/Dc/0/Voltage', 11.5)
		self._monitor.set_value('com.victronenergy.battery.ttyO5', '/Dc/0/Current', -60)
		self._monitor.set_value('com.victronenergy.battery.ttyO5', '/Soc', 60)
		self._update_values()
		self._check_values({
			'/State': 1,
			'/RunningByCondition': "soc"
		})

		self._monitor.set_value('com.victronenergy.battery.ttyO5', '/Soc', 70)
		self._update_values()
		self._check_values({
			'/State': 1,
			'/RunningByCondition': "acload"
		})

		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Ac/Out/L1/P', 200)
		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Ac/Out/L2/P', 200)
		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Ac/Out/L3/P', 200)
		self._update_values()
		self._check_values({
			'/State': 1,
			'/RunningByCondition': "batterycurrent"
		})

		self._monitor.set_value('com.victronenergy.battery.ttyO5', '/Dc/0/Current', -30)
		self._update_values()
		self._check_values({
			'/State': 1,
			'/RunningByCondition': "batteryvoltage"
		})

		self._monitor.set_value('com.victronenergy.battery.ttyO5', '/Dc/0/Voltage', 15)
		self._update_values()
		self._check_values({
			'/State': 0
		})


if __name__ == '__main__':
	unittest.main()
