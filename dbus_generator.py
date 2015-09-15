#!/usr/bin/python -u
# -*- coding: utf-8 -*-

# Function
# dbus_generator monitors the dbus for batteries (com.victronenergy.battery.*) and
# vebus com.victronenergy.vebus.*
# Battery and vebus monitors can be configured through the gui.
# It then monitors SOC, AC loads, battery current and battery voltage,to auto start/stop the generator based
# on the configuration settings. Generator can be started manually or periodically setting a maintenance period.
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
from dbusmonitor import DbusMonitor
from settingsdevice import SettingsDevice
from logger import setup_logging

softwareversion = '1.1'
dbusgenerator = None


class DbusGenerator:

    def __init__(self):
        self.RELAY_GPIO_FILE = '/sys/class/gpio/gpio182/value'
        self.HISTORY_DAYS = 30
        self._last_counters_check = 0
        self._dbusservice = None
        self._batteryservice = None
        self._starttime = 0
        self._manualstarttimer = 0
        self._last_runtime_update = 0
        self.timer_runnning = 0
        self.batteryservice_import = None
        self.bus = dbus.SystemBus() if (platform.machine() == 'armv7l') else dbus.SessionBus()

        self._condition_stack = {
            'batteryvoltage': {
                'name': 'batteryvoltage',
                'reached': False,
                'timed': True,
                'start_timer': 0,
                'stop_timer': 0,
                'valid': True,
                'enabled': False
            },
            'batterycurrent': {
                'name': 'batterycurrent',
                'reached': False,
                'timed': True,
                'start_timer': 0,
                'stop_timer': 0,
                'valid': True,
                'enabled': False
            },
            'acload': {
                'name': 'acload',
                'reached': False,
                'timed': True,
                'start_timer': 0,
                'stop_timer': 0,
                'valid': True,
                'enabled': False
            },
            'soc': {
                'name': 'soc',
                'reached': False,
                'timed': False,
                'valid': True,
                'enabled': False
            }
        }

        # DbusMonitor expects these values to be there, even though we don need them. So just
        # add some dummy data. This can go away when DbusMonitor is more generic.
        dummy = {'code': None, 'whenToLog': 'configChange', 'accessLevel': None}

        self._dbusmonitor = DbusMonitor({
            'com.victronenergy.vebus': {
                '/Connected': dummy,
                '/ProductName': dummy,
                '/Mgmt/Connection': dummy,
                '/State': dummy,
                '/Ac/Out/P': dummy,
                '/Dc/0/Current': dummy,
                '/Dc/0/Voltage': dummy,
                '/Dc/1/Power': dummy,
                '/Soc': dummy
            },
            'com.victronenergy.battery': {
                '/Connected': dummy,
                '/ProductName': dummy,
                '/Mgmt/Connection': dummy,
                '/Dc/0/Voltage': dummy,
                '/Dc/0/Current': dummy,
                '/Dc/0/Power': dummy,
                '/Dc/1/Voltage': dummy,
                '/Dc/1/Current': dummy,
                '/Dc/1/Power': dummy,
                '/Dc/2/Voltage': dummy,
                '/Dc/2/Current': dummy,
                '/Dc/2/Power': dummy,
                '/Soc': dummy
            },
            'com.victronenergy.settings': {   # This is not our setting so do it here. not in supportedSettings
                '/Settings/Relay/Function': dummy,
                '/Settings/Relay/Polarity': dummy,
                '/Settings/System/TimeZone': dummy,
                '/Settings/SystemSetup/BatteryService': dummy
                },
            'com.victronenergy.system': {   # This is not our setting so do it here. not in supportedSettings
                '/AvailableBatteryServices': dummy,
                '/Dc/Battery/Soc': dummy,
                '/Dc/Battery/Voltage': dummy,
                '/Dc/Battery/Current': dummy,
                '/Ac/Consumption/Total/Power': dummy,
                '/AutoSelectedBatteryMeasurement': dummy,
                }
        }, self._dbus_value_changed, self._device_added, self._device_removed)

        # Set timezone to user selected timezone
        environ['TZ'] = self._dbusmonitor.get_value('com.victronenergy.settings', '/Settings/System/TimeZone')

        # Connect to localsettings
        self._settings = SettingsDevice(
            bus=self.bus,
            supportedSettings={
                'autostart': ['/Settings/Generator/0/AutoStart', 0, 0, 1],
                'accumulateddaily': ['/Settings/Generator/0/AccumulatedDaily', '', 0, 0],
                'accumulatedtotal': ['/Settings/Generator/0/AccumulatedTotal', 0, 0, 0],
                'batteryservice': ['/Settings/Generator/0/BatteryService', "default", 0, 0],
                'minimumruntime': ['/Settings/Generator/0/MinimumRuntime', 0, 0, 86400],  # minutes
                # Time zones
                'timezonesenabled': ['/Settings/Generator/0/TimeZones/Enabled', 0, 0, 1],
                'timezonesstarttimer': ['/Settings/Generator/0/TimeZones/StartTime', 75600, 0, 86400],
                'timezonesendtime': ['/Settings/Generator/0/TimeZones/EndTime', 21600, 0, 86400],
                # SOC
                'socenabled': ['/Settings/Generator/0/Soc/Enabled', 0, 0, 1],
                'socstart': ['/Settings/Generator/0/Soc/StartValue', 90, 0, 100],
                'socstop': ['/Settings/Generator/0/Soc/StopValue', 90, 0, 100],
                'tz_socstart': ['/Settings/Generator/0/Soc/TimezoneStartValue', 90, 0, 100],
                'tz_socstop': ['/Settings/Generator/0/Soc/TimezoneStopValue', 90, 0, 100],
                # Voltage
                'batteryvoltageenabled': ['/Settings/Generator/0/BatteryVoltage/Enabled', 0, 0, 1],
                'batteryvoltagestart': ['/Settings/Generator/0/BatteryVoltage/StartValue', 11.5, 0, 150],
                'batteryvoltagestop': ['/Settings/Generator/0/BatteryVoltage/StopValue', 12.4, 0, 150],
                'batteryvoltagestarttimer': ['/Settings/Generator/0/BatteryVoltage/StartTimer', 20, 0, 10000],
                'batteryvoltagestoptimer': ['/Settings/Generator/0/BatteryVoltage/StopTimer', 20, 0, 10000],
                'tz_batteryvoltagestart': ['/Settings/Generator/0/BatteryVoltage/TimezoneStartValue', 11.9, 0, 100],
                'tz_batteryvoltagestop': ['/Settings/Generator/0/BatteryVoltage/TimezoneStopValue', 12.4, 0, 100],
                # Current
                'batterycurrentenabled': ['/Settings/Generator/0/BatteryCurrent/Enabled', 0, 0, 1],
                'batterycurrentstart': ['/Settings/Generator/0/BatteryCurrent/StartValue', 10.5, 0.5, 1000],
                'batterycurrentstop': ['/Settings/Generator/0/BatteryCurrent/StopValue', 5.5, 0, 1000],
                'batterycurrentstarttimer': ['/Settings/Generator/0/BatteryCurrent/StartTimer', 20, 0, 10000],
                'batterycurrentstoptimer': ['/Settings/Generator/0/BatteryCurrent/StopTimer', 20, 0, 10000],
                'tz_batterycurrentstart': ['/Settings/Generator/0/BatteryCurrent/TimezoneStartValue', 20.5, 0, 1000],
                'tz_batterycurrentstop': ['/Settings/Generator/0/BatteryCurrent/TimezoneStopValue', 15.5, 0, 1000],
                # AC load
                'acloadenabled': ['/Settings/Generator/0/AcLoad/Enabled', 0, 0, 1],
                'acloadstart': ['/Settings/Generator/0/AcLoad/StartValue', 1600, 5, 100000],
                'acloadstop': ['/Settings/Generator/0/AcLoad/StopValue', 800, 0, 100000],
                'acloadstarttimer': ['/Settings/Generator/0/AcLoad/StartTimer', 20, 0, 10000],
                'acloadstoptimer': ['/Settings/Generator/0/AcLoad/StopTimer', 20, 0, 10000],
                'tz_acloadstart': ['/Settings/Generator/0/AcLoad/TimezoneStartValue', 1900, 0, 100000],
                'tz_acloadstop': ['/Settings/Generator/0/AcLoad/TimezoneStopValue', 1200, 0, 100000],
                # Maintenance
                'maintenanceenabled': ['/Settings/Generator/0/Maintenance/Enabled', 0, 0, 1],
                'maintenancestartdate': ['/Settings/Generator/0/Maintenance/StartDate', time.time(), 0, 10000000000.1],
                'maintenancestarttimer': ['/Settings/Generator/0/Maintenance/StartTime', 54000, 0, 86400],
                'maintenanceinterval': ['/Settings/Generator/0/Maintenance/Interval', 28, 1, 365],
                'maintenanceruntime': ['/Settings/Generator/0/Maintenance/Duration', 7200, 1, 86400],
                'maintenanceskipruntime': ['/Settings/Generator/0/Maintenance/SkipRuntime', 0, 0, 100000]
            },
            eventCallback=self._handle_changed_setting)

        self._evaluate_if_we_are_needed()
        gobject.timeout_add(1000, self._handletimertick)
        self._changed = True

    def _evaluate_if_we_are_needed(self):
        if self._dbusmonitor.get_value('com.victronenergy.settings', '/Settings/Relay/Function') == 1:
            if self._dbusservice is None:
                logger.info('Action! Going on dbus and taking control of the relay.')
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
                # Maintenance runtime
                self._dbusservice.add_path('/MaintenanceIntervalRuntime',
                                           value=self._interval_runtime(self._settings['maintenanceinterval']),
                                           gettextcallback=self._gettext)
                # Next maintenance date, values is 0 for maintenande disabled
                self._dbusservice.add_path('/NextMaintenance', value=None, gettextcallback=self._gettext)
                # Next maintenance is needed 1, not needed 0
                self._dbusservice.add_path('/SkipMaintenance', value=None)
                # Manual start
                self._dbusservice.add_path('/ManualStart', value=0, writeable=True)
                # Manual start timer
                self._dbusservice.add_path('/ManualStartTimer', value=0, writeable=True)
                # Silent mode active
                self._dbusservice.add_path('/SecondaryTimeZone', value=0)

                self._determineservices()

                self._batteryservice = None
                self._acloadsource = None
                self._determineservices()

                if self._batteryservice is not None:
                    logger.info('Battery service we need (%s) found! Using it for generator start/stop'
                                % self._settings['batteryservice'].split("/")[0])

                elif self._acloadsource is not None:
                    logger.info('VE.Bus service we need (%s) found! Using it for generator start/stop'
                                % self._settings['batteryservice'].split("/")[0])
            else:
                self._determineservices()
        else:
            if self._dbusservice is not None:
                self._stop_generator()
                self._batteryservice = None
                self._acloadsource = None
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
        self._evaluate_if_we_are_needed()
        self._changed = True
        # Update relay state when polarity is changed
        if dbusPath == '/Settings/Relay/Polarity':
            self._update_relay()

    def _handle_changed_setting(self, setting, oldvalue, newvalue):
        self._changed = True
        self._evaluate_if_we_are_needed()
        if setting == 'Polarity':
            self._update_relay()
        if self._dbusservice is not None and setting == 'maintenanceinterval':
            self._dbusservice['/MaintenanceIntervalRuntime'] = self._interval_runtime(
                                                               self._settings['maintenanceinterval'])

    def _gettext(self, path, value):
        if path == '/NextMaintenance':
            # Locale format date
            d = datetime.datetime.fromtimestamp(value)
            return d.strftime('%c')
        elif path in ['/Runtime', '/MaintenanceIntervalRuntime', '/TodayRuntime']:
            m, s = divmod(value, 60)
            h, m = divmod(m, 60)
            return '%dh, %dm, %ds' % (h, m, s)
        else:
            return value

    def _handletimertick(self):
        # try catch, to make sure that we kill ourselves on an error. Without this try-catch, there would
        # be an error written to stdout, and then the timer would not be restarted, resulting in a dead-
        # lock waiting for manual intervention -> not good!
        # To keep accuracy, conditions will forced to be evaluated each second when the generator or a timer is running
        try:
            if self._dbusservice is not None and (self._changed or self._dbusservice['/State'] == 1
                                                  or self._dbusservice['/ManualStart'] == 1 or self.timer_runnning):
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
        conditions = ['soc', 'acload', 'batterycurrent', 'batteryvoltage']
        start = False
        runningbycondition = None
        today = calendar.timegm(datetime.date.today().timetuple())
        self.timer_runnning = False
        values = self._get_updated_values()

        self._check_secondary_timezone()

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

        # Evaluate value conditions
        for condition in conditions:
            start = self._evaluate_condition(self._condition_stack[condition], values[condition]) or start
            runningbycondition = condition if start and runningbycondition is None else runningbycondition

        if self._evaluate_maintenance_condition() and not start:
            runningbycondition = 'maintenance'
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
            logger.info('Error getting (%s) value, skipping evaluation till get a valid value' % name)
            self._reset_condition(condition)
            condition['valid'] = False
            return False

        elif value is not None and not condition['valid']:
            logger.info('Success getting (%s) value, resuming evaluation' % name)
            condition['valid'] = True

        return condition['valid']

    def _evaluate_condition(self, condition, value):
        name = condition['name']
        setting = ('tz_' if self._dbusservice['/SecondaryTimeZone'] == 1 else '') + name
        startvalue = self._settings[setting + 'start']
        stopvalue = self._settings[setting + 'stop']

        # Check if the have to be evaluated
        if not self._check_condition(condition, value):
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

    def _evaluate_maintenance_condition(self):
        if self._settings['maintenanceenabled'] == 0:
            self._dbusservice['/SkipMaintenance'] = None
            self._dbusservice['/NextMaintenance'] = None
            return False

        today = datetime.date.today()
        try:
            startdate = datetime.date.fromtimestamp(self._settings['maintenancestartdate'])
            starttime = time.mktime(today.timetuple()) + self._settings['maintenancestarttimer']
        except ValueError:
            logger.debug('Invalid dates, skipping maintenance')
            return False

        # If start date is in the future set as NextMaintenance and stop evaluating
        if startdate > today:
            self._dbusservice['/NextMaintenance'] = time.mktime(startdate.timetuple())
            return False

        start = False
        # If the accumulated runtime during the maintenance interval is greater than '/MaintenanceIntervalRuntime'
        # the maintenance must be skipped
        needed = (self._settings['maintenanceskipruntime'] > self._dbusservice['/MaintenanceIntervalRuntime']
                  or self._settings['maintenanceskipruntime'] == 0)
        self._dbusservice['/SkipMaintenance'] = int(not needed)

        interval = self._settings['maintenanceinterval']
        stoptime = starttime + self._settings['maintenanceruntime']
        elapseddays = (today - startdate).days
        mod = elapseddays % interval
        start = (not bool(mod) and (time.time() >= starttime) and (time.time() <= stoptime))

        if not bool(mod) and (time.time() <= stoptime):
            self._dbusservice['/NextMaintenance'] = starttime
        else:
            self._dbusservice['/NextMaintenance'] = (time.mktime((today +
                                                     datetime.timedelta(days=interval - mod)).timetuple()) +
                                                     self._settings['maintenancestarttimer'])
        return start and needed

    def _check_secondary_timezone(self):
        active = False
        if self._settings['timezonesenabled'] == 1:
            # Seconds after today 00:00
            timeinseconds = time.time() - time.mktime(datetime.date.today().timetuple())
            timezonesstart = self._settings['timezonesstarttimer']
            timezonesend = self._settings['timezonesendtime']

            # Check if the current time is between the start time and end time
            if timezonesstart < timezonesend:
                active = timezonesstart <= timeinseconds and timeinseconds < timezonesend
            else:  # End time is lower than start time, example Start: 21:00, end: 08:00
                active = not (timezonesend < timeinseconds and timeinseconds < timezonesstart)

        if self._dbusservice['/SecondaryTimeZone'] == 0 and active:
            logger.info('Entering to secondary timezone timezone')

        elif self._dbusservice['/SecondaryTimeZone'] == 1 and not active:
            logger.info('Leaving secondary timezone')

        self._dbusservice['/SecondaryTimeZone'] = int(active)

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
        self._dbusservice['/MaintenanceIntervalRuntime'] = self._interval_runtime(self._settings['maintenanceinterval'])

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
        values = {
            'batteryvoltage': None,
            'batterycurrent': None,
            'soc': None,
            'acload': None
        }
        if self._batteryservice is not None:
	        # Update values from battery monitor
	        batteryservice = self._batteryservice.split('/')[0]
	        battery = "/" + self._batteryservice.split('/', 1)[1]
        	values['soc'] = self._dbusmonitor.get_value(batteryservice, '/Soc')
        	values['batteryvoltage'] = self._dbusmonitor.get_value(batteryservice, battery + '/Voltage')
        	values['batterycurrent'] = self._dbusmonitor.get_value(batteryservice, battery + '/Current') * -1

        values['acload'] = self._dbusmonitor.get_value('com.victronenergy.system', '/Ac/Consumption/Total/Power')
        return values

    def _determineservices(self):
    	dummy = {'code': None, 'whenToLog': 'configChange', 'accessLevel': None}

    	if len(self._settings['batteryservice'].split("/")) < 3:
    		if self._settings['batteryservice'] == 'default':
    			service_auto = self._dbusmonitor.get_value('com.victronenergy.system','/AutoSelectedBatteryMeasurement')
    			batteryservicename = '/ServiceMapping/' + service_auto.split("/")[0]
    			battery_number = service_auto.split("/", 1)[1]
    		else:
    			self._batteryservice = None
	    		return
    	else:
    		batteryservicename = '/ServiceMapping/' + self._settings['batteryservice'].split("/")[0]
    		battery_number = self._settings['batteryservice'].split("/", 1)[1]
    		
    
    	if self.batteryservice_import is None:
    		self.batteryservice_import = VeDbusItemImport(bus = self.bus , serviceName = "com.victronenergy.system", path = batteryservicename, eventCallback=None, createsignal=True)
    	else:
    		if self.batteryservice_import.path != batteryservicename:
    			self.batteryservice_import = VeDbusItemImport(bus = self.bus , serviceName = "com.victronenergy.system", path = batteryservicename, eventCallback=None, createsignal=True)

        batteryservice =  self.batteryservice_import.get_value()
        self._batteryservice = batteryservice + "/" + battery_number if batteryservice != None else None
      
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
