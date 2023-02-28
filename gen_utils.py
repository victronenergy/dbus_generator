import sys
import os
import dbus
from vedbus import VeDbusService

from version import softwareversion

dummy = {'code': None, 'whenToLog': 'configChange', 'accessLevel': None}

class BaseEnum(object):
	@classmethod
	def lookup(klass, v):
		return klass._lookup[v]

def enum(**kw):
	c = type('Enum', (BaseEnum,), kw)
	c._lookup = { x.lower(): y for x, y in kw.items() }
	return c


class Errors(object):
	NONE, REMOTEDISABLED, REMOTEINFAULT = range(3)
	@staticmethod
	def get_description(value):
		description = [
		'No error',
		'Remote control disabled',
		'Remote in fault condition']
		d = ''
		try:
			d = description[value]
		except IndexError:
			pass
		return d

class States(object):
	STOPPED = 0
	RUNNING = 1
	WARMUP = 2
	COOLDOWN = 3
	ERROR = 10

	@staticmethod
	def get_description(value):
		description = [
			'Stopped',
			'Running',
			'Warm-up',
			'Cool-down'] + \
		6 * [''] + [
			'Error']
		d = ''
		try:
			d = description[value]
		except IndexError:
			pass
		return d

class SettingsPrefix(object):
	def __init__(self, settings, prefix):
		self._settings = settings
		self._prefix = prefix

	def removeprefix(self, setting):
		return setting.replace(self._prefix, "")

	def __getitem__(self, setting):
			return self._settings[setting + self._prefix]

	def __setitem__(self, setting, value):
		self._settings[setting + self._prefix] = value

def create_dbus_service(instance):
	# Use a private bus, so we can have multiple services
	bus = dbus.Bus.get_session(private=True) if 'DBUS_SESSION_BUS_ADDRESS' in os.environ else dbus.Bus.get_system(private=True)

	dbusservice = VeDbusService("com.victronenergy.generator.startstop{}".format(instance), bus=bus)
	dbusservice.add_mandatory_paths(
		processname=sys.argv[0],
		processversion=softwareversion,
		connection='generator',
		deviceinstance=instance,
		productid=None,
		productname=None,
		firmwareversion=None,
		hardwareversion=None,
		connected=1)
	return dbusservice
