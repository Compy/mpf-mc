"""Contains AssetManager, AssetLoader, and Asset parent classes."""

import copy
import os
import random
import sys
import threading
import traceback
from collections import deque
from queue import PriorityQueue, Queue, Empty

from kivy.clock import Clock

from mpf.system.config import CaseInsensitiveDict
from mpf.system.utility_functions import Util


class AssetManager(object):
    """Base class for the Asset Manager.

    Args:
        mc: The main MpfMc object.

    """

    def __init__(self, mc):

        # self.log = logging.getLogger(config_section + ' Asset Manager')
        # self.log.debug("Initializing...")

        self.mc = mc
        self._asset_classes = list()
        # List of dicts, with each dict being an asset class. See
        # register_asset_class() method for details.

        self.num_assets_to_load = 0
        # Total number of assets that are/will be loaded. Used for
        # calculating progress. Reset to 0 when num_assets_loaded matches it.

        self.num_assets_loaded = 0
        # Number of assets loaded so far. Reset to 0 when it hits
        # num_assets_to_load.

        self.num_bcp_assets_to_load = 0
        self.num_bcp_assets_loaded = 0
        self.num_bcb_assets_remaining = 0

        self.loader_queue = PriorityQueue()  # assets for to the loader thread
        self.loaded_queue = Queue()  # assets loaded from the loader thread
        self.loader_thread = None
        self._loaded_watcher = False

        self._start_loader_thread()

        self.mc.mode_controller.register_start_method(
                start_method=self._load_mode_assets)

        # Modes load in init_phase_1, so by 2 we have everything to create
        # the assets.
        self.mc.events.add_handler('init_phase_2', self._create_assets)

        # Picks up asset load information from connected BCP client(s)
        self.mc.events.add_handler('assets_to_load',
                                   self._bcp_client_asset_load)

    @property
    def num_assets_remaining(self):
        return self.num_assets_to_load - self.num_assets_loaded

    @property
    def loading_percent(self):
        """The percent of assets that are in the process of loading that have
        been loaded. This value is an integer between 0 and 100. It's reset
        when all the assets have been loaded, so it will go from 0 to 100 when
        MPF is starting up, and then go from 0 to 100 again when a mode starts,
        etc.

        Note that this percentage also includes asset loading status updates
        from a connected BCP client.
        """

        try:
            return round((self.num_assets_loaded +
                          self.num_bcp_assets_loaded) /
                         (self.num_assets_to_load +
                          self.num_bcp_assets_to_load) * 100)

        except ZeroDivisionError:
            return 100

    def shutdown(self):
        """Prepares the Asset Manager for shutdown by stopping the loader
        thread. Will block until the loader thread is stopped.

        """
        self.loader_queue = None
        self.loaded_queue = None
        self.loader_thread.stop()

    def _start_loader_thread(self):
        self.loader_thread = AssetLoader(self.loader_queue,
                                         self.loaded_queue,
                                         self.mc.crash_queue)
        # self.loader_thread.daemon = True
        self.loader_thread.start()

    def register_asset_class(self, asset_class, attribute, config_section,
                             path_string, extensions, priority,
                             group_config_section):
        """Registers a a type of assets to be controlled by the AssetManager.

        Args:
            asset_class: Reference to the class you want to register, based on
                mc.core.assets.Asset. e.g. mc.assets.images.ImageClass
            attribute: String of the name of the attribute dict that will be
                added to the main MpfMc instance. e.g. 'images' means that
                the dict of image names to image asset class instances will be
                at self.mc.images.
            config_section: String name of this assets section in the config
                files. e.g. 'images'
            path_string: String name of the setting from mpf_mc:paths: which
                controls the name of the folder that will hold this type of
                assets in the machine folder. e.g. 'images
            extensions: Tuple of strings, with no dots, of the types of file
                extensions that are valid for this type of asset. e.g. ('jpg',
                'gif', 'png')
            priority: Integer of the relative priority of this asset class as
                compared to other asset classes. This affects the order that
                asset objects are created and loaded (when there's a tie)
                because some asset classes depend on others to exist first.
                e.g. 'slide_shows' assets need 'images', 'videos', and 'sounds'
                to exist. Higher number is first.
            group_config_section: String which specifies the config file
                section for associated asset groups.

        """
        if not hasattr(self.mc, attribute):
            setattr(self.mc, attribute, CaseInsensitiveDict())

        else:  # pragma no cover
            raise ValueError('Cannot set self.mc.{} as it already '
                             'exists.'.format(attribute))

        ac = dict(attribute=attribute,
                  cls=asset_class,
                  path_string=path_string,
                  config_section=config_section,
                  extensions=extensions,
                  priority=priority,
                  group_config_section=group_config_section,
                  defaults=dict())

        self._asset_classes.append(ac)
        self._asset_classes.sort(key=lambda x: x['priority'], reverse=True)
        self._set_asset_class_defaults(ac, self.mc.machine_config)

    def _set_asset_class_defaults(self, asset_class, config):
        # Creates the folder-based default configs for the asset class
        # starting with the default section and then created folder-specific
        # entries based on that. Just runs once on startup for each asset
        # class.
        default_config_dict = dict()

        if 'assets' in config and config['assets']:

            if (asset_class['config_section'] in config['assets'] and
                    config['assets'][asset_class['config_section']]):

                this_config = config['assets'][asset_class['config_section']]

                # set the default
                default_config_dict['default'] = this_config.pop('default')

                for default_section_name in this_config:
                    # first get a copy of the default for this section
                    default_config_dict[default_section_name] = (
                        copy.deepcopy(default_config_dict['default']))

                    # then merge in this section's specific settings
                    default_config_dict[default_section_name].update(
                            this_config[default_section_name])

        asset_class['defaults'] = default_config_dict

    def _create_assets(self):
        # Called once on boot to create all the asset objects
        # Create the machine-wide assets
        self._create_assets_from_disk(config=self.mc.machine_config)
        self._create_asset_groups(config=self.mc.machine_config)

        # Create the mode assets
        for mode in self.mc.modes.values():
            self._create_assets_from_disk(config=mode.config, mode=mode)
            self._create_asset_groups(config=mode.config, mode=mode)

        # load the assets marked for preload:
        preload_assets = list()

        for ac in self._asset_classes:
            preload_assets.extend(
                    [x for x in getattr(self.mc, ac['attribute']).values() if
                     x.config['load'] == 'preload'])

        for asset in preload_assets:
            asset.load()

        if not preload_assets:
            self.mc.clear_boot_hold('assets')

    def _create_assets_from_disk(self, config, mode=None):
        """Walks a folder (and subfolders) and finds all the assets. Checks to
        see if those assets have config entries in the passed config file, and
        then builds a config for each asset based on its config entry, and/or
        defaults based on the subfolder it was in or the general defaults.
        Then it creates the asset objects based on the built-up config.

            Args:
                config: A config dictionary.
                mode: Optional reference to the mode object which is used when
                    assets are being created from mode folders.
                mode_path: Optional full path to the base folder that will be
                    traversed for the assets file on disk. If omitted, the
                    base machine folder will be searched.

            Returns: An updated config dictionary. (See the "How it works"
                section below for details.

        Note that this method merely creates the asset object so they can be
        referenced in MPF. It does not actually load the asset files into
        memory.

        It's called on startup register machine-wide assets, and it's called
        as modes initialize (also during the startup process) to find assets
        in mode folders.

        How it works
        ============

        Every asset class that's registered with the Asset Manager has a folder
        associated it. (e.g. Images assets as associated wit the "images"
        folder.)

        This method will build a master config dict of all the assets of each
        type. It does this by walking the folder, looking for files of each
        asset type.

        When it finds a file, it checks the config to see if either (1) any
        entries exist with a name that matches the root of that file name, or
        (2) to see if there's a config for an asset with a different name
        but with a file: setting that matches this file name.

        If it finds a match, that entry's file: setting is updated with the
        default settings for assets in that folder as well as the full path to
        the file. If it does not find a match, it creates a new entry for
        that asset in the config.

        To build up the config, it will base the config on any settings
        specified in the "default" section of the "assets:" section for that
        asset class. (e.g. images will get whatever key/value pairs are in the
        assets:images:default section of the config.)

        Then it will look to see what subfolder the asset it in and if there
        are any custom default settings for that subfolder. For example, an
        image found in the /custom1 subfolder will get any settings in the
        assets:images:custom1 section of the config. These settings are merged
        into the settings from the default section.

        Finally it will merge in any settings that existed for this asset
        specifically.

        When this method is done, the config dict has been updated to include
        every asset it found in that folder and subfolders (along with its
        full path), and a config dict appropriately merged from default,
        folder-specific, and asset specific settings

        """
        if not config:
            config = dict()

        try:
            mode_name = mode.name
            path = mode.path
        except AttributeError:
            mode_name = None
            path = self.mc.machine_path

        for ac in self._asset_classes:

            if ac['config_section'] not in config:
                config[ac['config_section']] = dict()

            # Populate the config section for this asset class with all the
            # assets found on disk
            config[ac['config_section']] = self._create_asset_config_entries(
                    asset_class=ac,
                    config=config[ac['config_section']],
                    mode_name=mode_name,
                    path=path)

            # create the actual instance of the Asset object and add it
            # to the self.mc asset attribute dict for that asset class
            for asset in config[ac['config_section']]:
                getattr(self.mc, ac['attribute'])[asset] = ac['cls'](
                        mc=self.mc, name=asset,
                        file=config[ac['config_section']][asset]['file'],
                        config=config[ac['config_section']][asset])

        return config

    def _create_asset_config_entries(self, asset_class, config, mode_name=None,
                                     path=None):
        """Scans a folder (and subfolders) and automatically creates or updates
        entries in the config dict for any asset files it finds.

        Args:
            asset_class: An asset class entry from the self._asset_classes
            dict.
            config: A dictionary which contains a list of asset names with
                settings that will be used for the specific asset. (Note this
                is not needed for all assets, as any asset file found not in
                the config dictionary will be set up with the folder it was
                found in's asset_defaults settings.)
            path: A full system path to the root folder that will be searched
                for assets. This should *not* include the asset-specific path
                string. If None, machine's root folder will be searched.

        Returns: Updated config dict that has all the new assets (and their
            built-up configs) that were found on disk.

        Note that for each file found, this method will scan through the
        entire config dict to see if any entry exists for that file based on an
        entry's 'file:' setting. If it's not found, an entry is created based
        on the file name. (This auto-created entry uses the lower-case stem of
        the file, e.g. a file called Image1.png will result in an asset entry
        called 'image1'.)

        Examples (based on images):

            asset_class defaults: section:
                default:
                    some_key: some_value
                foo:
                    some_key: some_value

            Based on the above asset_class defaults: section, the following
            files would get their 'defaults:' setting set to 'foo':
                /images/foo/image1.png
                /images/foo/bar/image2.png
                /images/foo/bar/bar2/image3.png

            And based on the above, the following files would get their
            'defaults:' setting set to 'default:
                /images/image4.png
                /images/foo/image5.png
                /images/other/images6.png
                /images/other/big/image7.png

        """
        if not path:
            path = self.mc.machine_path

        if not config:
            config = dict()

        root_path = os.path.join(path, asset_class['path_string'])

        # self.log.debug("Processing assets from base folder: %s", root_path)

        for path, _, files in os.walk(root_path, followlinks=True):

            valid_files = [f for f in files if f.endswith(
                    asset_class['extensions'])]

            for file_name in valid_files:
                folder = os.path.basename(path)
                name = os.path.splitext(file_name)[0].lower()
                full_file_path = os.path.join(path, file_name)

                if (folder == asset_class['path_string'] or
                            folder not in asset_class['defaults']):
                    default_string = 'default'
                else:
                    default_string = folder

                # built_up_config is the built-up config dict for that will be
                # used for the entry for this asset.

                # first deepcopy the default config for this asset based
                # on it's default_string (folder) since we use it as the base
                # for everything in case one of the custom folder configs
                # doesn't include all settings
                built_up_config = copy.deepcopy(
                        asset_class['defaults'][default_string])

                # scan through the existing config to see if this file is used
                # as the file setting for any entry.
                for k, v in config.items():

                    if ('file' in v and v['file'] == file_name) or name == k:
                        # if it's found, set the asset entry's name to whatever
                        # the name of this entry is
                        name = k
                        # merge in the config settings for this asset, updating
                        #  the defaults
                        built_up_config.update(config[k])
                        break

                # need to send the full file path to the Asset that will
                # be created so it will be able to load it later.
                built_up_config['file'] = full_file_path

                # If this asset is set to load on mode start, replace the load
                # value with one based on mode name
                if built_up_config['load'] == 'mode_start':
                    built_up_config['load'] = '{}_start'.format(mode_name)

                # Update the config for that asset
                config[name] = built_up_config

                # self.log.debug("Registering Asset: %s, File: %s, Default
                # Group: %s, Final Config: %s", name, file_name,
                #                default_string, built_up_config)

        return config

    def locate_asset_file(self, file_name, path_string, path=None):
        """Takes a file name and a root path and returns a link to the absolute
        path of the file

        Args:
            file_name: String of the file name
            path: root of the path to check (without the specific asset path
                string)

        Returns: String of the full path (path + file name) of the asset.

        Note this method will add the path string between the path you pass and
        the file. Also if it can't find the file in the path you pass, it will
        look for the file in the machine root plus the path string location.

        """
        if path:
            path_list = [path]
        else:
            path_list = list()

        path_list.append(self.mc.machine_path)

        for path in path_list:
            full_path = os.path.join(path, path_string, file_name)
            if os.path.isfile(full_path):
                return full_path

        # self.log.critical("Could not locate asset file '%s'. Quitting...",
        #                   file_name)
        raise ValueError("Could not locate image '{}'".format(file_name))

    def _create_asset_groups(self, config, mode=None):
        # creates named groups of assets and adds them to to the mc's asset
        # dicts
        for ac in [x for x in self._asset_classes
                   if x['group_config_section']]:

            if (ac['group_config_section']) not in config:
                return

            for name, settings in config[ac['group_config_section']].items():
                getattr(self.mc, ac['attribute'])[name] = (
                    ac['cls'].asset_group_class(self.mc, name, settings,
                                                ac['cls']))

    def _load_mode_assets(self, config, priority, mode):
        # Called on mode start to load the assets that are set to automatically
        # load based on that mode starting
        return (self.unload_assets,
                self.load_assets_by_load_key(
                        key_name='{}_start'.format(mode.name),
                        priority=priority))

    def load_assets_by_load_key(self, key_name, priority=0):
        """Loads all the assets with a given load key.

            Args:
                key_name: String of the load: key name.

        """
        assets = set()

        # loop through all the registered assets of each class and look for
        # this key name
        for ac in self._asset_classes:

            asset_objects = getattr(self.mc, ac['attribute']).values()

            for asset in [x for x in asset_objects if
                          x.config['load'] == key_name]:
                asset.load()
                assets.add(asset)

        return assets

    def unload_assets(self, assets):
        """Unloads multiple assets.

            Args:
                assets: An iterable of asset objects. You can safely mix
                    different classes of assets.

        """
        for asset in assets:
            asset.unload()

    def _load_asset(self, asset):
        # Internal method which handles the logistics of actually loading an
        # asset. Should only be called by Asset.load() as that method does
        # additional things that are needed.

        self.num_assets_to_load += 1

        # It's ok for an asset to make it onto this queue twice as the loader
        # thread will check the asset's loaded attribute to make sure it needs
        # to load it.

        # This is a PriorityQueue which will automatically put the asset into
        # the proper position in the queue based on its priority.

        self.loader_queue.put(asset)

        if not self._loaded_watcher:
            Clock.schedule_interval(self._check_loader_status, 0)
            self._loaded_watcher = True

    def _check_loader_status(self, *args):
        # checks the loaded queue and updates loading stats
        try:
            while not self.loaded_queue.empty():
                self.loaded_queue.get()._loaded()
                self.num_assets_loaded += 1
                self._post_loading_event()
        except AttributeError:
            pass

        if self.num_assets_to_load == self.num_assets_loaded:
            self.num_assets_loaded = 0
            self.num_assets_to_load = 0
            # print('Resetting loading counters')
            Clock.unschedule(self._check_loader_status)
            self._loaded_watcher = False

    def _bcp_client_asset_load(self, total, remaining):
        # Callback for the BCP assets_to_load command which tracks asset
        # loading from a connected BCP client.
        self.num_bcp_assets_loaded = int(total) - int(remaining)
        self.num_bcp_assets_to_load = int(total)
        self.num_bcb_assets_remaining = int(remaining)
        self._post_loading_event()

    def _post_loading_event(self):
        # Called each time an asset is loaded.
        total = self.num_assets_to_load + self.num_bcp_assets_to_load
        remaining = total - self.num_assets_loaded - self.num_bcp_assets_loaded

        self.mc.events.post('loading_assets', total=total,
                            loaded=self.num_assets_loaded +
                                   self.num_bcp_assets_loaded,
                            remaining=remaining,
                            percent=self.loading_percent)

        # TODO temp until logging is implemented properly
        print('Loading assets: {}/{} ({}%)'.format(self.num_assets_loaded +
                                                   self.num_bcp_assets_loaded,
                                                   total,
                                                   self.loading_percent))

        if not remaining and not self.mc.init_done:
            self.mc.clear_boot_hold('assets')


class AssetLoader(threading.Thread):
    """Base class for the Asset Loader thread and actually loads the assets
    from disk.

    Args:
        loader_queue: A reference to the asset manager's loader_queue which
            holds assets waiting to be loaded. Items are automatically sorted
            in reverse order by priority, then creation ID.
        loaded_queue: A reference to the asset manager's loaded_queue which
            holds assets that have just been loaded. Entries are Asset
            instances.
        exception_queue: Send a reference to self.mc.crash_queue. This way if
            the asset loader crashes, it will write the crash to that queue and
            cause an exception in the main thread. Otherwise it fails silently
            which is super annoying. :)

    """

    def __init__(self, loader_queue, loaded_queue, exception_queue):

        threading.Thread.__init__(self)
        # self.log = logging.getLogger('Asset Loader')
        self.loader_queue = loader_queue
        self.loaded_queue = loaded_queue
        self.exception_queue = exception_queue
        self._run = True
        self.name = 'asset_loader'

    def stop(self):
        """Stops the AssetLoader thread, blocking until the thread is stopped.
        This method also clears out the loader and loaded queues.

        """
        self._run = False

        if self.is_alive():
            self.join()

        while not self.loader_queue.empty():
            try:
                self.loader_queue.get_nowait()
            except Empty:
                pass

        while not self.loaded_queue.empty():
            try:
                self.loaded_queue.get_nowait()
            except Empty:
                pass

        self.loaded_queue = None
        self.loader_queue = None

    def run(self):
        """Run loop for the loader thread."""

        try:  # wrap the so we can send exceptions to the main thread
            while True:
                try:
                    asset = self.loader_queue.get(block=True, timeout=.1)
                except Empty:
                    asset = None

                if not self._run:
                    break

                if asset:
                    if not asset.loaded:
                        with asset.lock:
                            asset._do_load()

                    self.loaded_queue.put(asset)

        except Exception:  # pragma no cover
            exc_type, exc_value, exc_traceback = sys.exc_info()
            lines = traceback.format_exception(exc_type, exc_value,
                                               exc_traceback)
            msg = ''.join(line for line in lines)
            self.exception_queue.put(msg)


class AssetGroup(object):
    def __init__(self, mc, name, config, member_cls):
        self.mc = mc
        self.name = name
        self.config = config
        self.member_cls = member_cls
        self.loading_members = set()
        self._callbacks = set()
        self.assets = list()
        self._last_asset = None
        self._asset_sequence = deque()
        self._assets_sent = set()
        self._total_weights = 0

        if 'load' not in config:
            config['load'] = 'on_demand'

        if 'type' not in config:
            config['type'] = 'sequence'

        for asset in Util.string_to_list(self.config[
                                             self.member_cls.config_section]):
            try:
                name, number = asset.split('|')
                if not number:
                    number = 1
                else:
                    number = int(number)
            except ValueError:
                name = asset
                number = 1

            try:
                self.assets.append((
                    getattr(self.mc, self.member_cls.attribute)[name],
                    number))
            except KeyError:
                print("No asset named {}", name)

        self._configure_return_asset()

    def __repr__(self):
        # String that's returned if someone prints this object
        return '<AssetGroup: {}>'.format(self.name)

    @property
    def asset(self):
        if self.config['type'] == 'random':
            return self._get_random_asset()
        elif self.config['type'] == 'sequence':
            return self._get_sequence_asset()
        elif self.config['type'] == 'random_force_next':
            return self._get_random_force_next_asset()
        elif self.config['type'] == 'random_force_all':
            return self._get_random_force_all_asset()

    def _configure_return_asset(self):

        self._total_weights = sum([x[1] for x in self.assets])

        if self.config['type'] == 'sequence':
            for index in range(len(self.assets)):
                self._asset_sequence.extend([self.assets[index][0]] *
                                            self.assets[index][1])
            self._asset_sequence.rotate(1)

    def load(self, callback=None, priority=None):
        if priority is not None:
            self.priority = priority

        self._callbacks.add(callback)

        for asset in self.assets:
            if not asset[0].loaded:
                self.loading_members.add(asset)
                asset[0].load(callback=self._group_member_loaded)

        if not self.loading_members:
            self._call_callbacks()

    def _group_member_loaded(self, asset):
        self.loading_members.discard(asset)
        if not self.loading_members:
            self._call_callbacks()

    def _call_callbacks(self):
        for callback in self._callbacks:

            if callable(callback):
                callback(self)

        self._callbacks = set()

    def _get_random_asset(self):
        return self._pick_weighed_random(self.assets)[0]

    def _get_sequence_asset(self):
        self._asset_sequence.rotate(-1)
        return self._asset_sequence[0]

    def _get_random_force_next_asset(self):
        self._total_weights = sum([x[1] for x in self.assets
                                   if x is not self._last_asset])

        self._last_asset = self._pick_weighed_random([x for x in self.assets
                                                      if
                                                      x is not
                                                      self._last_asset])
        return self._last_asset[0]

    def _get_random_force_all_asset(self):
        if len(self._assets_sent) == len(self.assets):
            self._assets_sent = set()

        asset = self._pick_weighed_random([x for x in self.assets
                                           if x not in self._assets_sent])
        self._assets_sent.add(asset)
        return asset[0]

    def _pick_weighed_random(self, assets):
        value = random.randint(1, self._total_weights)
        index_value = assets[0][1]

        for asset in assets:
            if index_value >= value:
                return asset
            else:
                index_value += asset[1]

        return assets[-1]


class Asset(object):
    attribute = ''  # attribute in MC, e.g. self.mc.images
    path_string = ''  # entry from mpf_mc:paths: for asset folder name
    config_section = ''  # section in the config files for this asset
    extensions = ('', '', '')  # tuple of strings, no dots
    class_priority = 0  # Order asset classes will be loaded. Higher is first.
    group_config_section = None  # Create an associated AssetGroup instance
    asset_group_class = AssetGroup  # replace with your own asset group class

    _next_id = 0

    @classmethod
    def _get_id(cls):
        # Since the asset loader priority queue needs a way to break ties if
        # two assets are loading with the same priority, we need to implement
        # a comparison operator on the Asset, so we just increment and ID.
        # This means the assets will load in the order they were added to the
        # queue
        cls._next_id += 1
        return cls._next_id

    @classmethod
    def initialize(cls, mc):
        mc.asset_manager.register_asset_class(
                asset_class=cls,
                attribute=cls.attribute,
                path_string=cls.path_string,
                config_section=cls.config_section,
                extensions=cls.extensions,
                priority=cls.class_priority,
                group_config_section=cls.group_config_section)

    def __init__(self, mc, name, file, config):
        self.mc = mc
        self.name = name
        self.config = config
        self.file = file
        self.priority = config.get('priority', 0)
        self._callbacks = set()
        self._id = Asset._get_id()
        self.lock = threading.Lock()

        self.loading = False  # Is this asset in the process of loading?
        self.loaded = False  # Is this asset loaded and ready to use?
        self.unloading = False  # Is this asset in the process of unloading?

    def __repr__(self):
        return '<Asset: {}>'.format(self.name)

    def __lt__(self, other):
        # Note this is "backwards" (It's the __lt__ method but the formula uses
        # greater than because the PriorityQueue puts lowest first.)
        return ("%s, %s" % (self.priority, self._id) >
                "%s, %s" % (other.priority, other._id))

    def load(self, callback=None, priority=None):
        if priority is not None:
            self.priority = priority

        self._callbacks.add(callback)

        if self.loaded:
            self._call_callbacks()
            return

        if self.unloading:
            pass
            # do something fancy here. Maybe just skip it and come back?

        self.loading = True
        self.mc.asset_manager._load_asset(self)

    def _call_callbacks(self):
        for callback in self._callbacks:

            if callable(callback):
                callback(self)

        self._callbacks = set()

    def _do_load(self):
        # This is the actual method that loads the asset. It's called by a
        # different thread so it's ok to block. Make sure you don't set any
        # attributes here or you don't need any since it's a separate thread.
        raise NotImplementedError

    def _loaded(self):
        self.loading = False
        self.loaded = True
        self.unloading = False
        self._call_callbacks()

    def unload(self):
        self.unloading = True
        self.loaded = False
        self.loading = False
        self._do_unload()
        self.unloading = False

    def _do_unload(self):
        # This is the actual method that unloads the asset
        raise NotImplementedError

    def _unloaded(self):
        pass
