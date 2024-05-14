#!/usr/bin/env python3
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
import mock_glib
from logger import setup_logging
from mock_dbus_monitor import MockDbusMonitor
from mock_dbus_service import MockDbusService
from mock_settings_device import MockSettingsDevice
from gen_utils import Errors, States
import startstop

# Monkey-patch dbus connection
startstop.StartStop._create_dbus_service = lambda s: create_service(s)
startstop.WAIT_FOR_ENGINE_STOP = 1

def create_service(s):
	serv = MockDbusService('com.victronenergy.generator.startstop{}'.format(s._instance))
	# Mandatory paths are needed
	serv.add_mandatory_paths(
            processname="mock_dbus",
            processversion=1.0,
            connection='',
            deviceinstance=1,
            productid=None,
            productname=None,
            firmwareversion=None,
            hardwareversion=None,
            connected=1)
	return serv

class MockGenerator(dbus_generator.Generator):

	def _create_dbus_monitor(self, *args, **kwargs):
		return MockDbusMonitor(*args, **kwargs)

	def _create_settings(self, *args, **kwargs):
		self._settings = MockSettingsDevice(*args, **kwargs)
		return self._settings

class TestGeneratorBase(unittest.TestCase):
	def __init__(self, methodName='runTest'):
		unittest.TestCase.__init__(self, methodName)

	def setUp(self):
		mock_glib.timer_manager.reset()
		self._generator_ = MockGenerator()
		self._monitor = self._generator_._dbusmonitor

	def _update_values(self, interval=1000):
		if not self._services:
			self._services = {i._instance: i._dbusservice for i in self._generator_._instances.values()}
		mock_glib.timer_manager.add_terminator(interval)
		mock_glib.timer_manager.start()

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

	def _check_values(self, instance, values):
		ok = True
		for k, v in values.items():
			v2 = self._services[instance][k] if instance in self._services and k in self._services[instance] else None
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
		for k, v in values.items():
			msg += '{0}:\t{1}'.format(k, v)
			if instance in self._services and k in self._services[instance]:
				msg += '\t{}'.format(self._services[instance][k])
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
				'/Ac/ConsumptionOnOutput/L1/Power': 500,
				'/Ac/ConsumptionOnOutput/L2/Power': 500,
				'/Ac/ConsumptionOnOutput/L3/Power': 500,
				'/Ac/ConsumptionOnInput/L1/Power': 150,
				'/Ac/ConsumptionOnInput/L2/Power': 150,
				'/Ac/ConsumptionOnInput/L3/Power': 150,
				'/Dc/Pv/Power': 0,
				'/Dc/Battery/Current': 10,
				'/Dc/Battery/Voltage': 14.4,
				'/Dc/Battery/Soc': 87,
				'/Ac/ActiveIn/Source': 2,
				'/AutoSelectedBatteryMeasurement': "com_victronenergy_battery_258/Dc/0",
				'/VebusService': "com.victronenergy.vebus.ttyO1",
				'/Relay/0/State': 0
				})

		self._add_device('com.victronenergy.settings',
			values={
				'/Settings/Relay/Function': 1,
				'/Settings/System/TimeZone': 'Europe/Berlin',
				'/Settings/SystemSetup/AcInput1': 2,
				'/Settings/SystemSetup/AcInput2': 1,
			})

		self._add_device('com.victronenergy.genset.socketcan_can1_di0_uc0',
			values={
				'/Start': 0,
				'/RemoteStartModeEnabled': 1,
				'/Connected': 1,
				'/ProductId': 0xB040,
				'/ErrorCode': 0
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
				'/Ac/ActiveIn/ActiveInput': 1,
				'/Ac/ActiveIn/Connected': 0,
				'/Ac/State/AcIn1Available': None, # not supported in older firmware
				'/Ac/State/AcIn2Available': None,
				'/Ac/Control/IgnoreAcIn1': 0,
				'/Ac/Control/IgnoreAcIn2': 0,
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


		# DBus service is not created till Settings/Relay/Function is 1
		self._services = {i._instance: i._dbusservice for i in self._generator_._instances.values()}


	def test_acload_consumption(self):
		self._monitor.set_value('com.victronenergy.system', '/Ac/ConsumptionOnOutput/L1/Power', 1800)
		self._monitor.set_value('com.victronenergy.system', '/Ac/ConsumptionOnOutput/L2/Power', 50)
		self._monitor.set_value('com.victronenergy.system', '/Ac/ConsumptionOnOutput/L3/Power', 400)
		self._monitor.set_value('com.victronenergy.system', '/Ac/ConsumptionOnInput/L1/Power', 100)
		self._monitor.set_value('com.victronenergy.system', '/Ac/ConsumptionOnInput/L2/Power', 50)
		self._monitor.set_value('com.victronenergy.system', '/Ac/ConsumptionOnInput/L3/Power', 200)

		self._set_setting('/Settings/Generator0/AutoStartEnabled', 1)
		self._set_setting('/Settings/Generator0/AcLoad/Enabled', 1)
		self._set_setting('/Settings/Generator0/AcLoad/Measurement', 0)
		self._set_setting('/Settings/Generator0/AcLoad/StartValue', 2600)
		self._set_setting('/Settings/Generator0/AcLoad/StopValue', 800)
		self._set_setting('/Settings/Generator0/AcLoad/StartTimer', 0)
		self._set_setting('/Settings/Generator0/AcLoad/StopTimer', 0)

		self._update_values()
		self._check_values(0, {
			'/State': States.RUNNING
		})

	def test_activeinput(self):
		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Ac/Out/L1/P', 700)
		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Ac/Out/L2/P', 700)
		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Ac/Out/L3/P', 700)
		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Ac/ActiveIn/Connected', 1)
		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Ac/ActiveIn/ActiveInput', 1)
		self._set_setting('/Settings/Generator0/AutoStartEnabled', 1)
		self._set_setting('/Settings/Generator0/AcLoad/Enabled', 1)
		self._set_setting('/Settings/Generator0/AcLoad/Measurement', 1)
		self._set_setting('/Settings/Generator0/AcLoad/StartValue', 1650)
		self._set_setting('/Settings/Generator0/AcLoad/StopValue', 800)
		self._set_setting('/Settings/Generator0/AcLoad/StartTimer', 0)
		self._set_setting('/Settings/Generator0/AcLoad/StopTimer', 0)
		self._set_setting('/Settings/Generator0/StopWhenAc1Available', 1)

		self._update_values()
		self._check_values(0, {
			'/State': States.RUNNING
		})
		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Ac/ActiveIn/ActiveInput', 0)
		self._update_values()
		self._check_values(0, {
			'/State': States.STOPPED
		})
		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Ac/ActiveIn/Connected', 0)
		self._update_values()
		self._check_values(0, {
			'/State': States.RUNNING
		})
		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Ac/ActiveIn/Connected', 1)
		self._update_values()
		self._check_values(0, {
			'/State': States.STOPPED
		})

	def test_ac1_available(self):
		# Similar to above, but tests with readout support on the Quattro
		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Ac/Out/L1/P', 700)
		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Ac/Out/L2/P', 700)
		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Ac/Out/L3/P', 700)
		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Ac/ActiveIn/Connected', 1)
		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Ac/ActiveIn/ActiveInput', 1)
		self._monitor.set_value('com.victronenergy.system', '/Dc/Battery/Voltage', 11.5)
		self._monitor.set_value('com.victronenergy.system', '/Dc/Battery/Current', -60)
		self._monitor.set_value('com.victronenergy.system', '/Dc/Battery/Soc', 80)
		self._set_setting('/Settings/Generator0/AutoStartEnabled', 1)
		self._set_setting('/Settings/Generator0/AcLoad/Enabled', 1)
		self._set_setting('/Settings/Generator0/AcLoad/Measurement', 1)
		self._set_setting('/Settings/Generator0/AcLoad/StartValue', 1650)
		self._set_setting('/Settings/Generator0/AcLoad/StopValue', 800)
		self._set_setting('/Settings/Generator0/AcLoad/StartTimer', 0)
		self._set_setting('/Settings/Generator0/AcLoad/StopTimer', 0)
		self._set_setting('/Settings/Generator0/StopWhenAc1Available', 1)
		self._set_setting('/Settings/Generator0/Soc/Enabled', 1)
		self._set_setting('/Settings/Generator0/Soc/StartValue', 30)
		self._set_setting('/Settings/Generator0/Soc/StopValue', 70)

		self._update_values()
		self._check_values(0, {
			'/State': States.RUNNING
		})
		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Ac/State/AcIn1Available', 0)
		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Ac/ActiveIn/ActiveInput', 240)
		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Ac/ActiveIn/Connected', 0)
		self._update_values()
		self._check_values(0, {
			'/State': States.RUNNING
		})
		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Ac/State/AcIn1Available', 1)
		self._update_values()
		self._check_values(0, {
			'/State': States.STOPPED
		})

		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Ac/Out/L1/P', 100)
		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Ac/Out/L2/P', 100)
		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Ac/Out/L3/P', 100)

		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Ac/State/AcIn1Available', 0)
		self._update_values()
		self._check_values(0, {
			'/State': States.STOPPED
		})

		self._monitor.set_value('com.victronenergy.system', '/Dc/Battery/Soc', 20)
		self._update_values()
		self._check_values(0, {
			'/State': States.RUNNING
		})

		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Ac/State/AcIn1Available', 1)
		self._update_values()
		self._check_values(0, {
			'/State': States.STOPPED
		})

		# Check that conditions are reset after AC becomes unavailable again
		self._monitor.set_value('com.victronenergy.system', '/Dc/Battery/Soc', 40)
		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Ac/State/AcIn1Available', 0)
		self._update_values()
		self._check_values(0, {
			'/State': States.STOPPED
		})

	def test_ac2_available(self):
		# Test for stopping generator where firmware supports it.
		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Ac/Out/L1/P', 700)
		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Ac/Out/L2/P', 700)
		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Ac/Out/L3/P', 700)
		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Ac/ActiveIn/Connected', 1)
		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Ac/ActiveIn/ActiveInput', 0)
		self._monitor.set_value('com.victronenergy.system', '/Dc/Battery/Voltage', 11.5)
		self._monitor.set_value('com.victronenergy.system', '/Dc/Battery/Current', -60)
		self._monitor.set_value('com.victronenergy.system', '/Dc/Battery/Soc', 80)
		self._set_setting('/Settings/Generator0/AutoStartEnabled', 1)
		self._set_setting('/Settings/Generator0/AcLoad/Enabled', 1)
		self._set_setting('/Settings/Generator0/AcLoad/Measurement', 1)
		self._set_setting('/Settings/Generator0/AcLoad/StartValue', 1650)
		self._set_setting('/Settings/Generator0/AcLoad/StopValue', 800)
		self._set_setting('/Settings/Generator0/AcLoad/StartTimer', 0)
		self._set_setting('/Settings/Generator0/AcLoad/StopTimer', 0)
		self._set_setting('/Settings/Generator0/StopWhenAc1Available', 0)
		self._set_setting('/Settings/Generator0/StopWhenAc2Available', 1)
		self._set_setting('/Settings/Generator0/Soc/Enabled', 1)
		self._set_setting('/Settings/Generator0/Soc/StartValue', 30)
		self._set_setting('/Settings/Generator0/Soc/StopValue', 70)

		self._update_values()
		self._check_values(0, {
			'/State': States.RUNNING
		})
		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Ac/State/AcIn2Available', 0)
		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Ac/ActiveIn/ActiveInput', 240)
		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Ac/ActiveIn/Connected', 0)
		self._update_values()
		self._check_values(0, {
			'/State': States.RUNNING
		})
		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Ac/State/AcIn2Available', 1)
		self._update_values()
		self._check_values(0, {
			'/State': States.STOPPED
		})

		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Ac/Out/L1/P', 100)
		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Ac/Out/L2/P', 100)
		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Ac/Out/L3/P', 100)

		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Ac/State/AcIn2Available', 0)
		self._update_values()
		self._check_values(0, {
			'/State': States.STOPPED
		})

		self._monitor.set_value('com.victronenergy.system', '/Dc/Battery/Soc', 20)
		self._update_values()
		self._check_values(0, {
			'/State': States.RUNNING
		})

		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Ac/State/AcIn2Available', 1)
		self._update_values()
		self._check_values(0, {
			'/State': States.STOPPED
		})

		# Check that conditions are reset after AC becomes unavailable again
		self._monitor.set_value('com.victronenergy.system', '/Dc/Battery/Soc', 40)
		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Ac/State/AcIn2Available', 0)
		self._update_values()
		self._check_values(0, {
			'/State': States.STOPPED
		})

	def test_acload(self):
		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Ac/Out/L1/P', 700)
		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Ac/Out/L2/P', 700)
		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Ac/Out/L3/P', 700)
		self._set_setting('/Settings/Generator0/AutoStartEnabled', 1)
		self._set_setting('/Settings/Generator0/AcLoad/Enabled', 1)
		self._set_setting('/Settings/Generator0/AcLoad/Measurement', 1)
		self._set_setting('/Settings/Generator0/AcLoad/StartValue', 2200)
		self._set_setting('/Settings/Generator0/AcLoad/StopValue', 800)
		self._set_setting('/Settings/Generator0/AcLoad/StartTimer', 0)
		self._set_setting('/Settings/Generator0/AcLoad/StopTimer', 0)

		self._update_values()
		self._check_values(0, {
			'/State': States.STOPPED
		})
		self._set_setting('/Settings/Generator0/AcLoad/StartValue', 1650)
		self._update_values()
		self._check_values(0, {
			'/State': States.RUNNING
		})

	def test_dont_detect_generator(self):
		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Ac/Out/L1/P', 700)
		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Ac/Out/L2/P', 700)
		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Ac/Out/L3/P', 700)
		self._set_setting('/Settings/Generator0/AutoStartEnabled', 1)
		self._set_setting('/Settings/Generator0/AcLoad/Enabled', 1)
		self._set_setting('/Settings/Generator0/AcLoad/Measurement', 1)
		self._set_setting('/Settings/Generator0/AcLoad/StartValue', 2200)
		self._set_setting('/Settings/Generator0/AcLoad/StopValue', 800)
		self._set_setting('/Settings/Generator0/AcLoad/StartTimer', 0)
		self._set_setting('/Settings/Generator0/AcLoad/StopTimer', 0)
		self._set_setting('/Settings/Generator0/Alarms/NoGeneratorAtAcIn', 0)

		self._set_setting('/Settings/Generator0/AcLoad/StartValue', 1650)
		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Ac/ActiveIn/Connected', 0)
		self._monitor.set_value('com.victronenergy.system', '/Ac/ActiveIn/Source', 2)

		# Wait for generator
		self._update_values(320000)
		self._check_values(0, {
			'/Alarms/NoGeneratorAtAcIn': 0,
			'/State': States.RUNNING
		})

	def test_detect_generator(self):
		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Ac/Out/L1/P', 700)
		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Ac/Out/L2/P', 700)
		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Ac/Out/L3/P', 700)
		self._set_setting('/Settings/Generator0/AutoStartEnabled', 1)
		self._set_setting('/Settings/Generator0/AcLoad/Enabled', 1)
		self._set_setting('/Settings/Generator0/AcLoad/Measurement', 1)
		self._set_setting('/Settings/Generator0/AcLoad/StopValue', 800)
		self._set_setting('/Settings/Generator0/AcLoad/StartTimer', 0)
		self._set_setting('/Settings/Generator0/AcLoad/StopTimer', 0)
		self._set_setting('/Settings/Generator0/Alarms/NoGeneratorAtAcIn', 1)
		self._set_setting('/Settings/Generator0/WarmUpTime', 1)
		self._set_setting('/Settings/Generator0/CoolDownTime', 1)

		self._set_setting('/Settings/Generator0/AcLoad/StartValue', 1650)
		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Ac/ActiveIn/Connected', 0)
		self._monitor.set_value('com.victronenergy.system', '/Ac/ActiveIn/Source', 1)

		self._update_values(320000)
		self._check_values(0, {
			'/Alarms/NoGeneratorAtAcIn': 0,
			'/State': States.WARMUP
		})

		sleep(1)
		self._update_values(300000)
		self._check_values(0, {
			'/Alarms/NoGeneratorAtAcIn': 0,
			'/State': States.RUNNING
		})

		self._update_values()
		self._check_values(0, {
			'/Alarms/NoGeneratorAtAcIn': 2,
			'/State': States.RUNNING
		})

		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Ac/ActiveIn/Connected', 1)
		self._update_values(5000)
		self._check_values(0, {
			'/Alarms/NoGeneratorAtAcIn': 2,
			'/State': States.RUNNING
		})

		self._monitor.set_value('com.victronenergy.system', '/Ac/ActiveIn/Source', 2)
		self._update_values()
		self._check_values(0, {
			'/Alarms/NoGeneratorAtAcIn': 0,
			'/State': States.RUNNING
		})

		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Ac/ActiveIn/Connected', 0)
		self._update_values()
		self._check_values(0, {
			'/Alarms/NoGeneratorAtAcIn': 0,
			'/State': States.RUNNING
		})

		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Ac/Out/L1/P', 100)
		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Ac/Out/L2/P', 100)
		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Ac/Out/L3/P', 100)
		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Ac/ActiveIn/Connected', 0)
		self._update_values(301000)
		self._check_values(0, {
			'/Alarms/NoGeneratorAtAcIn': 0,
			'/State': States.COOLDOWN
		})

		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Ac/Out/L1/P', 700)
		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Ac/Out/L2/P', 700)
		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Ac/Out/L3/P', 700)
		self._update_values()

		sleep(1)
		self._update_values(300000)
		self._check_values(0, {
			'/Alarms/NoGeneratorAtAcIn': 2,
			'/State': States.RUNNING
		})

	def test_detect_generator_not_supported(self):
		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Ac/Out/L1/P', 700)
		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Ac/Out/L2/P', 700)
		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Ac/Out/L3/P', 700)
		self._set_setting('/Settings/Generator0/AutoStartEnabled', 1)
		self._set_setting('/Settings/Generator0/AcLoad/Enabled', 1)
		self._set_setting('/Settings/Generator0/AcLoad/Measurement', 1)
		self._set_setting('/Settings/Generator0/AcLoad/StopValue', 800)
		self._set_setting('/Settings/Generator0/AcLoad/StartTimer', 0)
		self._set_setting('/Settings/Generator0/AcLoad/StopTimer', 0)
		self._set_setting('/Settings/Generator0/Alarms/NoGeneratorAtAcIn', 1)

		self._set_setting('/Settings/Generator0/AcLoad/StartValue', 1650)
		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Ac/ActiveIn/Connected', None)
		self._monitor.set_value('com.victronenergy.system', '/Ac/ActiveIn/Source', 2)

		self._update_values(300000)
		self._check_values(0, {
			'/Alarms/NoGeneratorAtAcIn': 0,
			'/State': States.RUNNING
		})

		self._update_values()
		self._check_values(0, {
			'/Alarms/NoGeneratorAtAcIn': 0,
			'/State': States.RUNNING
		})

		self._update_values(5000)
		self._check_values(0, {
			'/Alarms/NoGeneratorAtAcIn': 0,
			'/State': States.RUNNING
		})

	def test_remote_error(self):
		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Ac/Out/L1/P', 700)
		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Ac/Out/L2/P', 700)
		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Ac/Out/L3/P', 700)
		self._set_setting('/Settings/Generator1/AutoStartEnabled', 1)
		self._set_setting('/Settings/Generator1/AcLoad/Enabled', 1)
		self._set_setting('/Settings/Generator1/AcLoad/Measurement', 1)
		self._set_setting('/Settings/Generator1/AcLoad/StartValue', 2200)
		self._set_setting('/Settings/Generator1/AcLoad/StopValue', 800)
		self._set_setting('/Settings/Generator1/AcLoad/StartTimer', 0)
		self._set_setting('/Settings/Generator1/AcLoad/StopTimer', 0)

		self._monitor.set_value('com.victronenergy.genset.socketcan_can1_di0_uc0', '/ErrorCode', 0)
		self._update_values()
		self._check_values(1, {
			'/State': States.STOPPED
		})
		self._set_setting('/Settings/Generator1/AcLoad/StartValue', 1650)
		self._update_values()
		self._check_values(1, {
			'/State': States.RUNNING
		})
		self._monitor.set_value('com.victronenergy.genset.socketcan_can1_di0_uc0', '/ErrorCode', 17)
		self._update_values()
		self._check_values(1, {
			'/State': States.ERROR,
			'/Error': Errors.REMOTEINFAULT
		})
		self._monitor.set_value('com.victronenergy.genset.socketcan_can1_di0_uc0', '/ErrorCode', 0)
		self._update_values()
		self._check_values(1, {
			'/State': States.RUNNING
		})

	def test_genset_autostart_disabled(self):
		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Ac/Out/L1/P', 700)
		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Ac/Out/L2/P', 700)
		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Ac/Out/L3/P', 700)
		self._set_setting('/Settings/Generator1/AutoStartEnabled', 1)
		self._set_setting('/Settings/Generator1/AcLoad/Enabled', 1)
		self._set_setting('/Settings/Generator1/AcLoad/Measurement', 1)
		self._set_setting('/Settings/Generator1/AcLoad/StartValue', 2200)
		self._set_setting('/Settings/Generator1/AcLoad/StopValue', 800)
		self._set_setting('/Settings/Generator1/AcLoad/StartTimer', 0)
		self._set_setting('/Settings/Generator1/AcLoad/StopTimer', 0)

		self._update_values()
		self._check_values(1, {
			'/State': States.STOPPED
		})
		self._set_setting('/Settings/Generator1/AcLoad/StartValue', 1650)
		self._update_values()
		self._check_values(1, {
			'/State': States.RUNNING
		})

		self._monitor.set_value('com.victronenergy.genset.socketcan_can1_di0_uc0', '/RemoteStartModeEnabled', 0)
		self._update_values()
		self._check_values(1, {
			'/State': States.ERROR,
			'/Error': Errors.REMOTEDISABLED
		})
		self._monitor.set_value('com.victronenergy.genset.socketcan_can1_di0_uc0', '/RemoteStartModeEnabled', 1)
		self._update_values()
		self._check_values(1, {
			'/State': States.RUNNING,
			'/Error': Errors.NONE
		})

	def test_overload_alarm_vebus(self):
		self._set_setting('/Settings/Generator0/AutoStartEnabled', 1)
		self._set_setting('/Settings/Generator0/InverterOverload/Enabled', 1)
		self._set_setting('/Settings/Generator0/InverterOverload/StartTimer', 0)
		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Alarms/L3/Overload', 1)

		self._update_values()
		self._check_values(0, {
			'/State': States.RUNNING,
			'/RunningByCondition': 'inverteroverload',
			'/RunningByConditionCode': 9
		})

	def test_hightemp_alarm_vebus(self):
		self._set_setting('/Settings/Generator0/AutoStartEnabled', 1)
		self._set_setting('/Settings/Generator0/InverterHighTemp/Enabled', 1)
		self._set_setting('/Settings/Generator0/InverterHighTemp/StartTimer', 0)
		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Alarms/L1/HighTemperature', 1)

		self._update_values()
		self._check_values(0, {
			'/State': States.RUNNING,
			'/RunningByCondition': 'inverterhightemp',
			'/RunningByConditionCode': 8
		})

	def test_hightemp_alarm_canbus(self):
		self._set_setting('/Settings/Generator0/AutoStartEnabled', 1)
		self._set_setting('/Settings/Generator0/InverterHighTemp/Enabled', 1)
		self._set_setting('/Settings/Generator0/InverterHighTemp/StartTimer', 0)
		# Multi connected to CAN-bus, doesn't have per-phase alarm paths, invalidate.
		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Alarms/L1/HighTemperature', None)
		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Alarms/L2/HighTemperature', None)
		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Alarms/L3/HighTemperature', None)
		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Alarms/HighTemperature', 1)

		self._update_values()
		self._check_values(0, {
			'/State': States.RUNNING,
			'/RunningByCondition': 'inverterhightemp',
			'/RunningByConditionCode': 8
		})

	def test_overload_alarm_canbus(self):
		self._set_setting('/Settings/Generator0/AutoStartEnabled', 1)
		self._set_setting('/Settings/Generator0/InverterOverload/Enabled', 1)
		self._set_setting('/Settings/Generator0/InverterOverload/StartTimer', 0)
		# Multi connected to CAN-bus, doesn't have per-phase alarm paths, invalidate.
		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Alarms/L1/Overload', None)
		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Alarms/L2/Overload', None)
		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Alarms/L3/Overload', None)
		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Alarms/Overload', 1)

		self._update_values()
		self._check_values(0, {
			'/State': States.RUNNING,
			'/RunningByCondition': 'inverteroverload',
			'/RunningByConditionCode': 9
		})

	def test_ac_highest_phase(self):
		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Ac/Out/L1/P', 550)
		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Ac/Out/L2/P', 660)
		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Ac/Out/L3/P', 500)
		self._update_values()
		self._set_setting('/Settings/Generator0/AutoStartEnabled', 1)
		self._set_setting('/Settings/Generator0/AcLoad/Enabled', 1)
		self._set_setting('/Settings/Generator0/AcLoad/Measurement', 2)
		self._set_setting('/Settings/Generator0/AcLoad/StartValue', 520)
		self._set_setting('/Settings/Generator0/AcLoad/StopValue', 500)
		self._set_setting('/Settings/Generator0/AcLoad/StartTimer', 0)
		self._set_setting('/Settings/Generator0/AcLoad/StopTimer', 0)

		self._update_values()
		self._check_values(0, {
			'/State': States.RUNNING
		})

	def test_manual_start(self):
		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Ac/ActiveIn/Connected', 1)
		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Ac/ActiveIn/ActiveInput', 1)
		self._set_setting('/Settings/Generator0/StopWhenAc1Available', 1)

		self._services[0]['/ManualStart'] = 1
		self._update_values()
		self._check_values(0, {
			'/State': States.RUNNING
		})
		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Ac/ActiveIn/ActiveInput', 0)
		self._update_values()
		self._check_values(0, {
			'/State': States.RUNNING
		})
		self._services[0]['/ManualStart'] = 0
		self._update_values()
		self._check_values(0, {
			'/State': States.STOPPED
		})

	def test_testrun(self):
		self._set_setting('/Settings/Generator0/AutoStartEnabled', 1)
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
		self._check_values(0, {
			'/State': States.STOPPED,
		})

		self._set_setting('/Settings/Generator0/TestRun/Interval', 1)
		self._update_values()
		self._check_values(0, {
			'/State': States.RUNNING,
		})

		sleep(1)
		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Ac/ActiveIn/ActiveInput', 0)
		self._update_values()
		self._check_values(0, {
			'/State': States.RUNNING
		})

		sleep(1)
		self._update_values()
		self._check_values(0, {
			'/State': States.STOPPED,
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
		self._check_values(0, {
			'/State': States.STOPPED
		})

	def test_testrun_battery_full(self):
		self._set_setting('/Settings/Generator0/AutoStartEnabled', 1)
		self._set_setting('/Settings/Generator0/TestRun/Enabled', 1)
		self._set_setting('/Settings/Generator0/TestRun/StartDate', self._yesterday())
		self._set_setting('/Settings/Generator0/TestRun/StartTime', self._seconds_since_midnight())
		self._set_setting('/Settings/Generator0/TestRun/Interval', 1)
		self._set_setting('/Settings/Generator0/TestRun/Duration', 0)
		self._set_setting('/Settings/Generator0/TestRun/SkipRuntime', 3600)
		self._set_setting('/Settings/Generator0/TestRun/RunTillBatteryFull', 1)
		self._monitor.set_value('com.victronenergy.system', '/Dc/Battery/Soc', 100)

		self._update_values()
		self._check_values(0, {
			'/State': States.STOPPED,
		})

		self._monitor.set_value('com.victronenergy.system', '/Dc/Battery/Soc', 70)
		self._update_values()
		self._check_values(0, {
			'/State': States.RUNNING,
		})

		self._monitor.set_value('com.victronenergy.system', '/Dc/Battery/Soc', 100)
		self._update_values()
		self._check_values(0, {
			'/State': States.STOPPED,
		})

	def test_comm_failure(self):
		self._monitor.set_value('com.victronenergy.system', '/Ac/ConsumptionOnOutput/L1/Power', 1800)
		self._monitor.set_value('com.victronenergy.system', '/Ac/ConsumptionOnOutput/L2/Power', 50)
		self._monitor.set_value('com.victronenergy.system', '/Ac/ConsumptionOnOutput/L3/Power', 400)
		self._monitor.set_value('com.victronenergy.system', '/Ac/ConsumptionOnInput/L1/Power', 100)
		self._monitor.set_value('com.victronenergy.system', '/Ac/ConsumptionOnInput/L2/Power', 50)
		self._monitor.set_value('com.victronenergy.system', '/Ac/ConsumptionOnInput/L3/Power', 200)

		self._set_setting('/Settings/Generator0/AutoStartEnabled', 1)
		self._set_setting('/Settings/Generator0/AcLoad/Enabled', 1)
		self._set_setting('/Settings/Generator0/AcLoad/Measurement', 0)
		self._set_setting('/Settings/Generator0/AcLoad/StartValue', 1600)
		self._set_setting('/Settings/Generator0/AcLoad/StopValue', 800)
		self._set_setting('/Settings/Generator0/AcLoad/StartTimer', 0)
		self._set_setting('/Settings/Generator0/AcLoad/StopTimer', 0)

		self._update_values()
		self._check_values(0, {
			'/State': States.RUNNING
		})

		self._remove_device("com.victronenergy.vebus.ttyO1")
		self._monitor.set_value('com.victronenergy.system', '/VebusService', None)

		self._update_values(300000)
		self._check_values(0, {
			'/State': States.RUNNING
		})

		self._update_values()
		self._check_values(0, {
			'/State': States.STOPPED
		})

	def test_comm_failure_continue_running(self):
		self._monitor.set_value('com.victronenergy.system', '/Ac/ConsumptionOnOutput/L1/Power', 1800)
		self._monitor.set_value('com.victronenergy.system', '/Ac/ConsumptionOnOutput/L2/Power', 50)
		self._monitor.set_value('com.victronenergy.system', '/Ac/ConsumptionOnOutput/L3/Power', 400)
		self._monitor.set_value('com.victronenergy.system', '/Ac/ConsumptionOnInput/L1/Power', 100)
		self._monitor.set_value('com.victronenergy.system', '/Ac/ConsumptionOnInput/L2/Power', 50)
		self._monitor.set_value('com.victronenergy.system', '/Ac/ConsumptionOnInput/L3/Power', 200)
		self._set_setting('/Settings/Generator0/AutoStartEnabled', 1)
		self._set_setting('/Settings/Generator0/OnLossCommunication', 2)
		self._set_setting('/Settings/Generator0/AcLoad/Enabled', 1)
		self._set_setting('/Settings/Generator0/AcLoad/Measurement', 0)
		self._set_setting('/Settings/Generator0/AcLoad/StartValue', 1600)
		self._set_setting('/Settings/Generator0/AcLoad/StopValue', 800)
		self._set_setting('/Settings/Generator0/AcLoad/StartTimer', 0)
		self._set_setting('/Settings/Generator0/AcLoad/StopTimer', 0)

		self._update_values()
		self._check_values(0, {
			'/State': States.RUNNING
		})
		self._remove_device("com.victronenergy.vebus.ttyO1")
		self._monitor.set_value('com.victronenergy.system', '/VebusService', None)

		self._update_values(300000)
		self._check_values(0, {
			'/State': States.RUNNING
		})

		self._update_values()
		self._check_values(0, {
			'/State': States.RUNNING
		})

	def test_comm_failure_start(self):
		self._monitor.set_value('com.victronenergy.system', '/Ac/ConsumptionOnOutput/L1/Power', 25)
		self._monitor.set_value('com.victronenergy.system', '/Ac/ConsumptionOnOutput/L2/Power', 15)
		self._monitor.set_value('com.victronenergy.system', '/Ac/ConsumptionOnOutput/L3/Power', 15)
		self._monitor.set_value('com.victronenergy.system', '/Ac/ConsumptionOnInput/L1/Power', 25)
		self._monitor.set_value('com.victronenergy.system', '/Ac/ConsumptionOnInput/L2/Power', 10)
		self._monitor.set_value('com.victronenergy.system', '/Ac/ConsumptionOnInput/L3/Power', 10)

		self._set_setting('/Settings/Generator0/AutoStartEnabled', 1)
		self._set_setting('/Settings/Generator0/OnLossCommunication', 1)
		self._set_setting('/Settings/Generator0/AcLoad/Enabled', 1)
		self._set_setting('/Settings/Generator0/AcLoad/Measurement', 0)
		self._set_setting('/Settings/Generator0/AcLoad/StartValue', 1600)
		self._set_setting('/Settings/Generator0/AcLoad/StopValue', 800)
		self._set_setting('/Settings/Generator0/AcLoad/StartTimer', 0)
		self._set_setting('/Settings/Generator0/AcLoad/StopTimer', 0)

		self._remove_device("com.victronenergy.vebus.ttyO1")
		self._monitor.set_value('com.victronenergy.system', '/VebusService', None)

		self._update_values(299000)
		self._check_values(0, {
			'/State': States.STOPPED
		})

		self._update_values()
		self._check_values(0, {
			'/State': States.RUNNING
		})

	def test_comm_failure_battery(self):
		self._set_setting('/Settings/Generator0/AutoStartEnabled', 1)
		self._set_setting('/Settings/Generator0/OnLossCommunication', 0)
		self._set_setting('/Settings/Generator0/BatteryCurrent/Enabled', 1)
		self._set_setting('/Settings/Generator0/BatteryCurrent/StartValue', 60)
		self._set_setting('/Settings/Generator0/BatteryCurrent/StopValue', 30)
		self._set_setting('/Settings/Generator0/BatteryCurrent/StartTimer', 0)
		self._set_setting('/Settings/Generator0/BatteryCurrent/StopTimer', 0)
		self._monitor.set_value('com.victronenergy.system', '/Dc/Battery/Current', -60)

		self._update_values()
		self._check_values(0, {
			'/State': States.RUNNING
		})

		self._monitor.set_value('com.victronenergy.system', '/AutoSelectedBatteryMeasurement', None)
		self._monitor.set_value('com.victronenergy.system', '/Dc/Battery/Current', None)
		self._update_values(300000)
		self._check_values(0, {
			'/State': States.RUNNING
		})

		self._update_values()
		self._check_values(0, {
			'/State': States.STOPPED
		})

	def test_comm_failure_battery_continue_running(self):
		self._set_setting('/Settings/Generator0/AutoStartEnabled', 1)
		self._set_setting('/Settings/Generator0/OnLossCommunication', 2)
		self._set_setting('/Settings/Generator0/BatteryCurrent/Enabled', 1)
		self._set_setting('/Settings/Generator0/BatteryCurrent/StartValue', 60)
		self._set_setting('/Settings/Generator0/BatteryCurrent/StopValue', 30)
		self._set_setting('/Settings/Generator0/BatteryCurrent/StartTimer', 0)
		self._set_setting('/Settings/Generator0/BatteryCurrent/StopTimer', 0)
		self._monitor.set_value('com.victronenergy.system', '/Dc/Battery/Current', -60)

		self._update_values()
		self._check_values(0, {
			'/State': States.RUNNING
		})

		self._monitor.set_value('com.victronenergy.system', '/AutoSelectedBatteryMeasurement', None)
		self._monitor.set_value('com.victronenergy.system', '/Dc/Battery/Current', None)

		self._update_values(300000)
		self._check_values(0, {
			'/State': States.RUNNING
		})

		self._update_values(5000)
		self._check_values(0, {
			'/State': States.RUNNING
		})

	def test_comm_failure_battery_start(self):
		self._set_setting('/Settings/Generator0/AutoStartEnabled', 1)
		self._set_setting('/Settings/Generator0/OnLossCommunication', 1)
		self._set_setting('/Settings/Generator0/BatteryCurrent/Enabled', 1)
		self._set_setting('/Settings/Generator0/BatteryCurrent/StartValue', 60)
		self._set_setting('/Settings/Generator0/BatteryCurrent/StopValue', 30)
		self._set_setting('/Settings/Generator0/BatteryCurrent/StartTimer', 0)
		self._set_setting('/Settings/Generator0/BatteryCurrent/StopTimer', 0)
		self._monitor.set_value('com.victronenergy.system', '/Dc/Battery/Current', 0)

		self._update_values()
		self._check_values(0, {
			'/State': States.STOPPED
		})

		self._monitor.set_value('com.victronenergy.system', '/AutoSelectedBatteryMeasurement', None)
		self._monitor.set_value('com.victronenergy.system', '/Dc/Battery/Current', None)

		self._update_values(299000)
		self._check_values(0, {
			'/State': States.STOPPED
		})

		self._update_values()
		self._check_values(0, {
			'/State': States.RUNNING
		})

	def test_disable_autostart(self):
		self._set_setting('/Settings/Generator0/AutoStartEnabled', 1)
		self._set_setting('/Settings/Generator0/BatteryCurrent/Enabled', 1)
		self._set_setting('/Settings/Generator0/BatteryCurrent/StartValue', 60)
		self._set_setting('/Settings/Generator0/BatteryCurrent/StopValue', 30)
		self._set_setting('/Settings/Generator0/BatteryCurrent/StartTimer', 0)
		self._set_setting('/Settings/Generator0/BatteryCurrent/StopTimer', 0)
		self._monitor.set_value('com.victronenergy.system', '/Dc/Battery/Current', -60)

		self._update_values()
		self._check_values(0, {
			'/State': States.RUNNING
		})
		self._set_setting('/Settings/Generator0/AutoStartEnabled', 0)
		self._update_values()
		self._check_values(0, {
			'/State': States.STOPPED
		})

	def test_disable_autostart_manual(self):
		self._set_setting('/Settings/Generator0/AutoStartEnabled', 0)
		self._services[0]['/ManualStart'] = 1
		self._update_values()
		self._check_values(0, {
			'/State': States.RUNNING
		})

	def test_minimum_runtime(self):
		self._set_setting('/Settings/Generator0/AutoStartEnabled', 1)
		self._set_setting('/Settings/Generator0/MinimumRuntime', 0.010)  # Minutes
		self._set_setting('/Settings/Generator0/BatteryCurrent/Enabled', 1)
		self._set_setting('/Settings/Generator0/BatteryCurrent/StartValue', 60)
		self._set_setting('/Settings/Generator0/BatteryCurrent/StopValue', 30)
		self._set_setting('/Settings/Generator0/BatteryCurrent/StartTimer', 0)
		self._set_setting('/Settings/Generator0/BatteryCurrent/StopTimer', 0)
		self._monitor.set_value('com.victronenergy.system', '/Dc/Battery/Current', -60)

		self._update_values()
		self._check_values(0, {
			'/State': States.RUNNING
		})

		self._monitor.set_value('com.victronenergy.system', '/Dc/Battery/Current', 0)
		self._update_values()
		self._check_values(0, {
			'/State': States.RUNNING
		})

		sleep(1)
		self._update_values()
		self._check_values(0, {
			'/State': States.STOPPED
		})

	def test_timed_condition(self):
		self._set_setting('/Settings/Generator0/AutoStartEnabled', 1)
		self._set_setting('/Settings/Generator0/MinimumRuntime', 0.010)  # Minutes
		self._set_setting('/Settings/Generator0/BatteryCurrent/Enabled', 1)
		self._set_setting('/Settings/Generator0/BatteryCurrent/StartValue', 60)
		self._set_setting('/Settings/Generator0/BatteryCurrent/StopValue', 30)
		self._set_setting('/Settings/Generator0/BatteryCurrent/StartTimer', 1)
		self._set_setting('/Settings/Generator0/BatteryCurrent/StopTimer', 1)
		self._monitor.set_value('com.victronenergy.system', '/Dc/Battery/Current', -60)

		self._update_values()
		self._check_values(0, {
			'/State': States.STOPPED
		})

		sleep(1)

		self._update_values()
		self._check_values(0, {
			'/State': States.RUNNING
		})

		self._monitor.set_value('com.victronenergy.system', '/Dc/Battery/Current', 0)

		self._update_values()
		self._check_values(0, {
			'/State': States.RUNNING
		})

		sleep(1)
		self._update_values()
		self._check_values(0, {
			'/State': States.STOPPED
		})

	def test_quiethours(self):
		self._set_setting('/Settings/Generator0/AutoStartEnabled', 1)
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

		self._monitor.set_value('com.victronenergy.system', '/Dc/Battery/Current', -60)

		self._update_values()
		self._check_values(0, {
			'/State': States.RUNNING
		})
		self._set_setting('/Settings/Generator0/QuietHours/StartTime', self._seconds_since_midnight())
		self._update_values()
		self._check_values(0, {
			'/State': States.STOPPED
		})
		self._set_setting('/Settings/Generator0/QuietHours/StartTime', self._seconds_since_midnight() - 1)
		self._set_setting('/Settings/Generator0/QuietHours/EndTime', self._seconds_since_midnight())
		self._update_values()
		self._check_values(0, {
			'/State': States.RUNNING
		})

	def test_soc_timer(self):
		self._set_setting('/Settings/Generator0/AutoStartEnabled', 1)
		self._set_setting('/Settings/Generator0/Soc/Enabled', 1)
		self._set_setting('/Settings/Generator0/Soc/StartValue', 60)
		self._set_setting('/Settings/Generator0/Soc/StopValue', 70)
		self._set_setting('/Settings/Generator0/Soc/StartTimer', 2)
		self._set_setting('/Settings/Generator0/Soc/StopTimer', 2)
		self._monitor.set_value('com.victronenergy.system', '/Dc/Battery/Soc', 60)

		self._update_values()

		self._check_values(0, {
			'/State': States.STOPPED
		})

		sleep(1)
		self._update_values()
		self._check_values(0, {
			'/State': States.STOPPED
		})

		sleep(1)
		self._update_values()
		self._check_values(0, {
			'/State': States.RUNNING,
			'/RunningByCondition': "soc",
			'/RunningByConditionCode': 4
		})

		self._monitor.set_value('com.victronenergy.system', '/Dc/Battery/Soc', 90)
		self._update_values()

		sleep(1)
		self._update_values()
		self._check_values(0, {
			'/State': States.RUNNING,
			'/RunningByCondition': "soc",
			'/RunningByConditionCode': 4
		})

		sleep(1)
		self._update_values()
		self._check_values(0, {
			'/State': States.STOPPED
		})

	def test_condition_cascade(self):
		self._set_setting('/Settings/Generator0/AutoStartEnabled', 1)
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
		self._monitor.set_value('com.victronenergy.system', '/Dc/Battery/Voltage', 11.5)
		self._monitor.set_value('com.victronenergy.system', '/Dc/Battery/Current', -60)
		self._monitor.set_value('com.victronenergy.system', '/Dc/Battery/Soc', 60)
		self._update_values()
		self._check_values(0, {
			'/State': States.RUNNING,
			'/RunningByCondition': "soc",
			'/RunningByConditionCode': 4
		})

		self._monitor.set_value('com.victronenergy.system', '/Dc/Battery/Soc', 70)
		self._update_values()
		self._check_values(0, {
			'/State': States.RUNNING,
			'/RunningByCondition': "acload",
			'/RunningByConditionCode': 5
		})

		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Ac/Out/L1/P', 200)
		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Ac/Out/L2/P', 200)
		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Ac/Out/L3/P', 200)
		self._update_values()
		self._check_values(0, {
			'/State': States.RUNNING,
			'/RunningByCondition': "batterycurrent",
			'/RunningByConditionCode': 6
		})

		self._monitor.set_value('com.victronenergy.system', '/Dc/Battery/Current', -30)
		self._update_values()
		self._check_values(0, {
			'/State': States.RUNNING,
			'/RunningByCondition': "batteryvoltage",
			'/RunningByConditionCode': 7
		})

		self._monitor.set_value('com.victronenergy.system', '/Dc/Battery/Voltage', 15)
		self._update_values()
		self._check_values(0, {
			'/State': States.STOPPED
		})

	def test_cascade_manual_battery_service(self):
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

		# Invalidate systemcalc battery values to make sure the script is not getting
		# them form it
		self._monitor.set_value('com.victronenergy.system', '/Dc/Battery/Voltage', None)
		self._monitor.set_value('com.victronenergy.system', '/Dc/Battery/Current', None)
		self._monitor.set_value('com.victronenergy.system', '/Dc/Battery/Soc', None)

		# Manual battery service selection is deprecated in favour of using the
		# calculated values from systemcalc but we still need to be compatible
		# for old installations where the selected battery service is not the
		# used by the system.
		self._set_setting('/Settings/Generator0/BatteryService', 'com_victronenergy_battery_258/Dc/0')
		self._set_setting('/Settings/Generator0/AutoStartEnabled', 1)

		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Ac/Out/L1/P', 600)
		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Ac/Out/L2/P', 850)
		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Ac/Out/L3/P', 550)
		self._monitor.set_value('com.victronenergy.battery.ttyO5', '/Dc/0/Voltage', 11.5)
		self._monitor.set_value('com.victronenergy.battery.ttyO5', '/Dc/0/Current', -60)
		self._monitor.set_value('com.victronenergy.battery.ttyO5', '/Soc', 60)
		self._update_values()
		self._check_values(0, {
			'/State': States.RUNNING,
			'/RunningByCondition': "soc",
			'/RunningByConditionCode': 4
		})

		self._monitor.set_value('com.victronenergy.battery.ttyO5', '/Soc', 70)
		self._update_values()
		self._check_values(0, {
			'/State': States.RUNNING,
			'/RunningByCondition': "acload",
			'/RunningByConditionCode': 5
		})

		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Ac/Out/L1/P', 200)
		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Ac/Out/L2/P', 200)
		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Ac/Out/L3/P', 200)
		self._update_values()
		self._check_values(0, {
			'/State': States.RUNNING,
			'/RunningByCondition': "batterycurrent",
			'/RunningByConditionCode': 6
		})

		self._monitor.set_value('com.victronenergy.battery.ttyO5', '/Dc/0/Current', -30)
		self._update_values()
		self._check_values(0, {
			'/State': States.RUNNING,
			'/RunningByCondition': "batteryvoltage",
			'/RunningByConditionCode': 7
		})

		self._monitor.set_value('com.victronenergy.battery.ttyO5', '/Dc/0/Voltage', 15)
		self._update_values()
		self._check_values(0, {
			'/State': States.STOPPED
		})

	def test_warmup_and_cooldown(self):
		self._set_setting('/Settings/Generator0/WarmUpTime', 1)
		self._set_setting('/Settings/Generator0/CoolDownTime', 1)
		self._services[0]['/ManualStart'] = 1
		self._update_values()
		self._check_values(0, {
			'/State': States.WARMUP
		})

		# Test that generator input is ignored during warmup
		self.assertEqual(self._monitor.get_value('com.victronenergy.vebus.ttyO1',
			'/Ac/Control/IgnoreAcIn1'), 1)
		self.assertEqual(self._monitor.get_value('com.victronenergy.vebus.ttyO1',
			'/Ac/Control/IgnoreAcIn2'), 0)

		sleep(1)
		self._update_values()
		self._check_values(0, {
			'/State': States.RUNNING
		})

		self._services[0]['/ManualStart'] = 0
		self._update_values()
		self._check_values(0, {
			'/State': States.COOLDOWN
		})

		# Test that generator input is ignored during cooldown
		self.assertEqual(self._monitor.get_value('com.victronenergy.vebus.ttyO1',
			'/Ac/Control/IgnoreAcIn1'), 1)
		self.assertEqual(self._monitor.get_value('com.victronenergy.vebus.ttyO1',
			'/Ac/Control/IgnoreAcIn2'), 0)

		# Wait for engine to stop, AC is ignored
		sleep(1)
		self._update_values()
		self._check_values(0, {
			'/State': States.STOPPING
		})
		self.assertEqual(self._monitor.get_value('com.victronenergy.vebus.ttyO1',
			'/Ac/Control/IgnoreAcIn1'), 1)
		self.assertEqual(self._monitor.get_value('com.victronenergy.vebus.ttyO1',
			'/Ac/Control/IgnoreAcIn2'), 0)

		# Engine has stopped, re-enable AC
		sleep(1)
		self._update_values()
		self._check_values(0, {
			'/State': States.STOPPED
		})
		self.assertEqual(self._monitor.get_value('com.victronenergy.vebus.ttyO1',
			'/Ac/Control/IgnoreAcIn1'), 0)
		self.assertEqual(self._monitor.get_value('com.victronenergy.vebus.ttyO1',
			'/Ac/Control/IgnoreAcIn2'), 0)

	def test_warmup_and_cooldown_ac2(self):
		self._set_setting('/Settings/Generator0/WarmUpTime', 1)
		self._set_setting('/Settings/Generator0/CoolDownTime', 1)

		# Genset is on AC2
		self._monitor.set_value('com.victronenergy.settings', '/Settings/SystemSetup/AcInput1', 1)
		self._monitor.set_value('com.victronenergy.settings', '/Settings/SystemSetup/AcInput2', 2)

		self._services[0]['/ManualStart'] = 1
		self._update_values()
		self._check_values(0, {
			'/State': States.WARMUP
		})

		# Test that generator input is ignored during warmup
		self.assertEqual(self._monitor.get_value('com.victronenergy.vebus.ttyO1',
			'/Ac/Control/IgnoreAcIn1'), 0)
		self.assertEqual(self._monitor.get_value('com.victronenergy.vebus.ttyO1',
			'/Ac/Control/IgnoreAcIn2'), 1)

		sleep(1)
		self._update_values()
		self._check_values(0, {
			'/State': States.RUNNING
		})

		self._services[0]['/ManualStart'] = 0
		self._update_values()
		self._check_values(0, {
			'/State': States.COOLDOWN
		})

		# Test that generator input is ignored during cooldown
		self.assertEqual(self._monitor.get_value('com.victronenergy.vebus.ttyO1',
			'/Ac/Control/IgnoreAcIn1'), 0)
		self.assertEqual(self._monitor.get_value('com.victronenergy.vebus.ttyO1',
			'/Ac/Control/IgnoreAcIn2'), 1)

		# Wait for engine to stop, AC is ignored
		sleep(1)
		self._update_values()
		self._check_values(0, {
			'/State': States.STOPPING
		})
		self.assertEqual(self._monitor.get_value('com.victronenergy.vebus.ttyO1',
			'/Ac/Control/IgnoreAcIn1'), 0)
		self.assertEqual(self._monitor.get_value('com.victronenergy.vebus.ttyO1',
			'/Ac/Control/IgnoreAcIn2'), 1)

		# Engine has stopped, re-enable AC
		sleep(1)
		self._update_values()
		self._check_values(0, {
			'/State': States.STOPPED
		})
		self.assertEqual(self._monitor.get_value('com.victronenergy.vebus.ttyO1',
			'/Ac/Control/IgnoreAcIn1'), 0)
		self.assertEqual(self._monitor.get_value('com.victronenergy.vebus.ttyO1',
			'/Ac/Control/IgnoreAcIn2'), 0)

	def test_capabilities_no_warmupcooldown(self):
		self._check_values(0, {'/Capabilities': 0})
		self._monitor.set_value('com.victronenergy.vebus.ttyO1', '/Ac/State/AcIn1Available', 1)
		self._check_values(0, {'/Capabilities': 1}) # Startup and Cooldown is supported

if __name__ == '__main__':
	# patch dbus_generator with mock glib
	dbus_generator.GLib = mock_glib

	unittest.main()
