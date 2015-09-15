#!/usr/bin/env python
# -*- coding: utf-8 -*-

import unittest
import dbus
import platform
import random
import time
import calendar
import datetime
import json
import sys
from subprocess import Popen, PIPE
from os import environ


class TestGenerator(unittest.TestCase):

    def setUp(self):
        self.bus = dbus.SystemBus() if (platform.machine() == 'armv7l') else dbus.SessionBus()
        self._settingspath = 'com.victronenergy.settings'
        self._generatorpath = 'com.victronenergy.generator.startstop0'
        self.batteryservice = 'com.victronenergy.battery.tty22'
        self.vebusservice = 'com.victronenergy.vebus.tty23'
        self.set_value(self._settingspath, "/Settings/Relay/Function", 1)
        self.fill_history()
        self.set_value(self._settingspath, "/Settings/Generator/0/BatteryService", "com_victronenergy_battery_223/Dc/0")
        self.firstRun = False
        self.reset_all_conditons()
        if (platform.machine() == 'armv7l'):
            environ['TZ'] = self.get_value(self._settingspath, '/Settings/System/TimeZone')

    def tearDown(self):
        pass

    def start_services(self):
        unittest.batteryp = Popen([sys.executable, "dummybattery.py"], stdout=PIPE, stderr=PIPE)
        unittest.vebusp = Popen([sys.executable, "dummyvebus.py"], stdout=PIPE, stderr=PIPE)
        while unittest.vebusp.stderr.readline().find(":/Soc") == -1:
            pass

    def stop_services(self):
        unittest.vebusp.kill()
        unittest.batteryp.kill()
        unittest.batteryp.wait()

    def reset_all_conditons(self):
        # Invert the relay polarity randomly
        self.polarity = abs(self.get_value(self._settingspath, '/Settings/Relay/Polarity') - 1)
        self.set_value(self._settingspath, '/Settings/Relay/Polarity', self.polarity)
        self.set_condition("Soc", 0, 0, 0)
        self.set_condition_timed("BatteryCurrent", 0, 0, 0, 0, 0)
        self.set_condition_timed("BatteryVoltage", 0, 0, 0, 0, 0)
        self.set_condition_timed("AcLoad", 0, 0, 0, 0, 0)
        self.set_value(self._settingspath, '/Settings/Generator/0/Maintenance/Enabled', 0)
        self.set_value(self._settingspath, '/Settings/Generator/0/TimeZones/Enabled', 0)
        self.set_value(self._settingspath, '/Settings/Generator/0/MinimumRuntime', 0)
        self.set_value(self._generatorpath, '/ManualStart', 0)
        self.set_value(self._generatorpath, '/ManualStartTimer', 0)
        time.sleep(2)  # Make sure generator stops

    def fill_history(self):
        today = calendar.timegm(datetime.date.today().timetuple())
        history = dict()
        for i in range(30):
            date = today - (i * 86400)
            history[str(date)] = random.randint(1800, 3600)
        self.set_value(self._settingspath, '/Settings/Generator/0/AccumulatedDaily', json.dumps(history, sort_keys=True))
        self.set_value(self._settingspath, '/Settings/Generator/0/AccumulatedTotal', sum(history.values()))

    def test_timed_condition(self):
        # Make the condition timer start setting current value to start/stop value
        # then set current value off the condition start/stop value, it should reset the timer.

        startvalue = random.uniform(-30, -11)
        stopvalue = random.uniform(-10, -1)
        starttimer = random.randint(5, 10)
        stoptimer = random.randint(5, 10)

        self.set_value(self.batteryservice, '/Dc/0/Current', startvalue + 1)

        # Start
        self.set_condition_timed("BatteryCurrent", -startvalue, -stopvalue, starttimer, stoptimer, 1)
        self.set_value(self.batteryservice, '/Dc/0/Current', startvalue)
        self.assertEqual(0, self.get_state(3))
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
        self.assertEqual(0, self.get_state(3))

    def test_minimum_runtime(self):
        self.set_value(self._settingspath, '/Settings/Generator/0/MinimumRuntime', 1)
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

    def test_maintenance(self):
        # The random generated history is set to a maximum of one hour per day, setting the maintenance
        # accumulated time to 10h and the interval to a maximum of 9 days makes sure that the maintenace
        # will not be skipped.

        today = calendar.timegm(datetime.date.today().timetuple())
        interval = random.randint(1, 9)
        setdate = today - (interval * 86400)
        currenttime = time.time() - time.mktime(datetime.date.today().timetuple())

        self.set_value(self._settingspath, '/Settings/Generator/0/Maintenance/Enabled', 1)
        self.set_value(self._settingspath, '/Settings/Generator/0/Maintenance/SkipRuntime', 36000)
        self.set_value(self._settingspath, '/Settings/Generator/0/Maintenance/StartDate', setdate)
        self.set_value(self._settingspath, '/Settings/Generator/0/Maintenance/StartTime', currenttime)
        self.set_value(self._settingspath, '/Settings/Generator/0/Maintenance/Interval', interval)
        self.set_value(self._settingspath, '/Settings/Generator/0/Maintenance/Duration', 15)
        self.set_value(self._settingspath, '/Settings/Generator/0/Maintenance/Enabled', 1)

        self.assertEqual(1, self.get_state(3))
        self.assertEqual(1, self.get_state(7))
        self.assertEqual(0, self.get_state(8))

        # Change the accumulated time to one hour, maintenance should be skipped
        self.set_value(self._settingspath, '/Settings/Generator/0/Maintenance/SkipRuntime', 3600)

        self.assertEqual(1, self.wait_and_get('/SkipMaintenance', 2))
        self.assertEqual(0, self.get_state(0))

    def test_timezones_mode(self):

        currenttime = time.time() - time.mktime(datetime.date.today().timetuple())
        self.set_value(self._settingspath, '/Settings/Generator/0/TimeZones/StartTime', currenttime)
        self.set_value(self._settingspath, '/Settings/Generator/0/TimeZones/EndTime', currenttime + 20)

        self.set_value(self.batteryservice, '/Dc/0/Current', -15)
        self.set_condition_timed("BatteryCurrent", 15, 10, 2, 2, 1)
        self.set_condition_timed("BatteryCurrent", 25, 15, 2, 2, 1, True)

        # Battery current condition must make generator start
        self.assertEqual(1, self.wait_and_get('/State', 5))
        self.set_value(self._settingspath, '/Settings/Generator/0/TimeZones/Enabled', 1)

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
        # Conditions order: Manual, Soc, AcLoad, BatteryCurrent, BatteryVoltage, Maintenance
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
        self.set_value(self._settingspath, '/Settings/Generator/0/Maintenance/SkipRuntime', 36000)
        self.set_value(self._settingspath, '/Settings/Generator/0/Maintenance/Interval', 1)
        self.set_value(self._settingspath, '/Settings/Generator/0/Maintenance/StartTime', currenttime)
        self.set_value(self._settingspath, '/Settings/Generator/0/Maintenance/Duration', 60)
        self.set_value(self._settingspath, '/Settings/Generator/0/Maintenance/Enabled', 1)

        self.set_value(self._generatorpath, '/ManualStart', 1)

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

        self.assertEqual('maintenance', self.wait_and_get('/RunningByCondition', stoptimer + 2))
        self.assertGreaterEqual(self.get_value(self._generatorpath, '/Runtime'), 11)

        self.set_value(self._settingspath, '/Settings/Generator/0/Maintenance/Enabled', 0)

        self.assertEqual(0,  self.get_state(2))

    def test_remove_battery_service(self):
        self.set_value(self.batteryservice, '/Dc/0/Current', -15)
        self.set_condition_timed("BatteryCurrent", 14, 10, 0, 5, 1)
        self.assertEqual(1, self.get_state(2))
        self.stop_services()
        self.assertEqual(0, self.get_state(2))
        self.start_services()
        self.set_value(self.batteryservice, '/Dc/0/Current', -15)
        self.assertEqual(1, self.get_state(2))

    def test_remove_vebus_service(self):
        self.set_value(self.vebusservice, '/Ac/Out/L1/P', 15)
        self.set_condition_timed("AcLoad", 14, 10, 0, 5, 1)
        self.assertEqual(1, self.get_state(2))
        self.stop_services()
        self.assertEqual(0, self.get_state(2))
        self.start_services()
        self.set_value(self.vebusservice, '/Ac/Out/L1/P', 15)
        self.assertEqual(1, self.get_state(3))

    def test_go_off(self):
        self.set_value(self.vebusservice, '/Ac/Out/L1/P', 15)
        self.set_condition_timed("AcLoad", 14, 10, 5, 5, 1)
        self.assertEqual(1, self.get_state(8))
        # Set relay function to alarm relay
        self.set_value(self._settingspath, "/Settings/Relay/Function", 0)
        time.sleep(3)
        # Set relay funtion to generator start/stop
        self.set_value(self._settingspath, "/Settings/Relay/Function", 1)
        # When the service go off all timers are reset, at this point generator
        # must be stopped
        self.assertEqual(0, self.get_state(3))
        # Timer finished, generator must be started
        self.assertEqual(1, self.get_state(5))

    def wait_and_get(self, setting, delay):
        time.sleep(delay)
        return self.get_value(self._generatorpath, setting)

    def get_state(self, delay):
        state = self.wait_and_get('/State', delay)
        if platform.machine() == 'armv7l':
            try:
                relay_gpio_file = open("/sys/class/gpio/gpio182/value", 'r')
                r = relay_gpio_file.read(1)
                relay_gpio_file.close()
            except IOError:
                print ('Error reading the relay file!')

            relayon = abs(int(r) - self.polarity)
            self.assertEqual(relayon, state)  # State and relay gpio file must have the same value
            return relayon

        return state

    def set_condition_timed(self, condition, start, stop, startimer, stoptimer, enabled, emergency=False, *arglist):
        settings = ({"StartValue": start, "StopValue": stop, "StartTimer": startimer,
                     "StopTimer": stoptimer, "Enabled": enabled})
        if emergency:
            settings["TimezoneStartValue"] = settings.pop("StartValue")
            settings["TimezoneStopValue"] = settings.pop("StopValue")
        for s, v in settings.iteritems():
            self.set_value(self._settingspath, "/Settings/Generator/0/" + condition + "/" + s, v)

    def set_condition(self, condition, start, stop, enabled, emergency=False):
        settings = ({"StartValue": start, "StopValue": stop, "Enabled": enabled})
        if emergency:
            settings["TimezoneStartValue"] = settings.pop("StartValue")
            settings["TimezoneStopValue"] = settings.pop("StopValue")
        for s, v in settings.iteritems():
            self.set_value(self._settingspath, "/Settings/Generator/0/" + condition + "/" + s, v)

    def set_value(self, path, setting, value):
        dbusobject = dbus.Interface(self.bus.get_object(path, setting), None)
        dbusobject.SetValue(value)

    def get_value(self, path, setting):
        dbusobject = dbus.Interface(self.bus.get_object(path, setting), None)
        return dbusobject.GetValue()

if __name__ == '__main__':
    # As the evaluation of the conditions is performed once per second and applying settings takes a while,
    # a safety delay of 3 extra seconds is added when checking values.
    for i in range(1):
        unittest.batteryp = Popen([sys.executable, "dummybattery.py"], stdout=PIPE, stderr=PIPE)
        unittest.vebusp = Popen([sys.executable, "dummyvebus.py"], stdout=PIPE, stderr=PIPE)
        while unittest.vebusp.stderr.readline().find(":/Soc") == -1:
            pass
        unittest.main(exit=False)
        unittest.vebusp.kill()
        unittest.batteryp.kill()
        unittest.batteryp.wait()
