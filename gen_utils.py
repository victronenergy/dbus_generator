dummy = {'code': None, 'whenToLog': 'configChange', 'accessLevel': None}

class BaseEnum(object):
	@classmethod
	def lookup(klass, v):
		return klass._lookup[v]

def enum(**kw):
	c = type('Enum', (BaseEnum,), kw)
	c._lookup = { x.lower(): y for x, y in kw.iteritems() }
	return c


class Errors:
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

class States:
	STOPPED = 0
	RUNNING = 1
	ERROR = 10

	@staticmethod
	def get_description(value):
		description = [
		'Stopped',
		'Running',
		'Error']
		d = ''
		try:
			d = description[value]
		except IndexError:
			pass
		return d

class SettingsPrefix:
	def __init__(self, settings, prefix):
		self._settings = settings
		self._prefix = prefix

	def removeprefix(self, setting):
		return setting.replace(self._prefix, "")

	def __getitem__(self, setting):
			return self._settings[setting + self._prefix]

	def __setitem__(self, setting, value):
		self._settings[setting + self._prefix] = value

class DBusServicePrefix:
	def __init__(self, service, prefix):
		self._service = service
		self._prefix = "/" + prefix

	def add_path(self, path, value, description="", writeable=False,
					onchangecallback=None, gettextcallback=None):
		self._service.add_path(self._prefix + path, value, description,
							writeable, onchangecallback, gettextcallback)

	def __delitem__(self, path):
		self._service.__delitem__(self._prefix + path)

	def __getitem__(self, path):
			return self._service[self._prefix + path]

	def __setitem__(self, path, value):
		self._service[self._prefix + path] = value
