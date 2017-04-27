import importlib
import logging
import os

from pyplanet.core.exceptions import ImproperlyConfigured, InvalidAppModule


class _AppContext:
	def __init__(self, app):
		"""
		Initiate the App Context. Used by several core and contribs to have it's own manager instance per app.
		You should always use the managers of your local app at first!
		
		:param app: App Config instance.
		:type app: pyplanet.apps.config.AppConfig
		"""
		self.ui = app.instance.ui_manager.create_app_manager(app)
		self.setting = app.instance.setting_manager.create_app_manager(app)


class AppConfig:
	"""
	This class is the base class for the Applications metadata class. The class holds information and hooks
	that will be executed after initiation for example.
	"""

	name = None
	label = None
	human_name = None
	path = None

	app_dependencies = None
	"""
	You can provide a list of dependencies to other apps (each entry needs to be a string of the app label!)
	"""

	mode_dependencies = None
	"""
	You can provide a list of gamemodes that are required to activate the app. Gamemodes needs to be declared as
	script names.
	You can override this behaviour by defining the following method in your config class
	
	.. code-block :: python

		def is_mode_supported(self, mode):
			return mode.startswith('TimeAttack')

	"""

	game_dependencies = None
	"""
	You can provide a list of game dependencies that needs to meet when the app is started. For example you can provide:

	.. code-block :: python

		game_dependencies = ['trackmania']

	You can override this behaviour by defining the following method in your config class
	
	.. code-block :: python

		def is_game_supported(self, game):
			return game != 'questmania'

	"""

	def __init__(self, app_name, app_module, instance):
		"""
		Init app config.
		
		:param app_name: App Name (from module path).
		:param app_module: App Module.
		:param instance: Instance of controller
		:type app_name: str
		:type app_module: str
		:type instance: pyplanet.core.instance.Instance
		"""
		# The full python module path. The postfix `*.app.*Config` is always the same!
		# Example: pyplanet.contrib.apps.games.trackmania.app.TrackmaniaConfig
		self.name = app_name

		# The apps root module.
		# Example: pyplanet.contrib.apps.games.trackmania
		self.module = app_module

		# The apps registry will be injected into the app config.
		self.apps = None

		# Make sure we give the core attribute the default value of false. This indicates if it's an internally
		# module.
		self.core = getattr(self, 'core', False)

		# The label can be given by the module, or automatically determinated on the last component.
		if not hasattr(self, 'label') or getattr(self, 'label', None) is None:
			self.label = app_name.rpartition('.')[2]

			# If the module is a core contrib module, we give the label a prefix (contrib.app).
			if self.core is True:
				self.label = 'core.{}'.format(self.label)

		# Human-readable name for the application eg. `MyApp`.
		if not hasattr(self, 'human_name') or getattr(self, 'human_name', None) is None:
			self.human_name = self.label.title()

		# Filesystem path to the application directory eg.
		if not hasattr(self, 'path') or getattr(self, 'path') is None:
			self.path = self._path_from_module(app_module)

		# The instance and related app context managers.
		self.instance = instance
		self.context = _AppContext(self)

	def __repr__(self):
		return '<%s: %s>' % (self.__class__.__name__, self.label)

	@property
	def ui(self):
		logging.warning(DeprecationWarning(
			'AppConfig.ui is deprecated, use AppConfig.context.ui instead.'
			'This is done to prevent collisions in future changes or feature adding.'
			'Calling app.ui from app \'{}\''.format(self.label)
		))
		return self.context.ui

	###################################################################################################
	# Lifecycle Methods
	###################################################################################################

	async def on_init(self):
		"""
		The on_init will be called before all apps are started (just before the on_ready). This will allow the app
		to register things like commands, permissions and other things that are important and don't require other
		apps to be ready.
		"""

	async def on_start(self):
		"""
		The on_start call is being called after all apps has been started successfully. You should register any stuff 
		that is related to any other apps and signals like your `self` context for signals if they are classmethods.
		"""
		# Deprecated: Fix the deprecated method
		if hasattr(self, 'on_ready'):
			logging.warning('on_ready is deprecated, use on_start instead! app: {}'.format(self.label))
			await self.on_ready()
		pass

	async def on_stop(self):
		"""
		The on_stop will be called before stopping the app.  
		"""
		pass

	async def on_destroy(self):
		"""
		On destroy is being called when unloading the app from the memory.
		"""
		pass

	###################################################################################################

	def is_mode_supported(self, mode):
		return self.mode_dependencies or mode in self.mode_dependencies

	def is_game_supported(self, game):
		return self.game_dependencies or game in self.game_dependencies

	def _path_from_module(self, module):
		"""Attempt to determine app's filesystem path from its module."""
		paths = list(getattr(module, '__path__', []))

		if len(paths) != 1:
			filename = getattr(module, '__file__', None)
			if filename is not None:
				paths = [os.path.dirname(filename)]
			else:
				# Can be bugged for unknown reasons.
				paths = list(set(paths))

		if len(paths) > 1:
			raise ImproperlyConfigured(
				'The app module {} has multiple filesystem locations {}; '
				'you must configure this app with an AppConfig subclass '
				'with a \'path\' class attribute.'.format(module, paths))

		elif not paths:
			raise ImproperlyConfigured(
				'The app module {} has no filesystem location, '
				'you must configure this app with an AppConfig subclass '
				'with a \'path\' class attribute.'.format(module))

		return paths[0]

	@staticmethod
	def import_app(entry, instance):
		# Import the module, we need to strip down the path into namespace, file and class.
		module_path, _, cls_name = entry.rpartition('.')
		if not module_path:
			raise ImproperlyConfigured('Module for your app {} can\'t be found!'.format(entry))

		# Try to load the app module, containing the class.
		try:
			module = importlib.import_module(module_path)
			module = getattr(module, cls_name)
		except ImportError:
			raise ImproperlyConfigured(
				'Can\'t load the app {}. Can\'t find the app config!'.format(entry)
			)
		except AttributeError as e:
			raise ImproperlyConfigured(
				'Can\'t load the app {}. Can\'t load the app class!'.format(entry)
			) from e

		# Last check if subclass of appconfig.
		if not issubclass(module, AppConfig):
			raise InvalidAppModule('Your required app {} couldn\'t be loaded!'.format(entry))

		# Get name and other attributes.
		try:
			app_name = module.name
			if app_name is None:
				raise AttributeError()
		except AttributeError:
			raise ImproperlyConfigured(
				'App {} must supply a name attribute.'.format(entry)
			)

		# Ensure app_name points to a valid module.
		try:
			app_module = importlib.import_module(app_name)
		except ImportError:
			raise ImproperlyConfigured(
				'Can\'t import {}. Check that \'{}.{}.name\' is correct.'.format(
					app_name, module_path, cls_name
				)
			)

		return module(app_name, app_module, instance)
