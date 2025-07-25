import sys
import os
import re
import json
import zipfile
import shutil
from fnmatch import fnmatch
import datetime
import tempfile
# To prevent import errors in thread with datetime
import locale  # noqa

try:
    # Python 3
    from urllib.parse import urlencode, urlparse
    import compileall
    str_cls = str
except (ImportError):
    # Python 2
    from urllib import urlencode
    from urlparse import urlparse
    str_cls = unicode  # noqa

import sublime

from .show_error import show_error
from .console_write import console_write
from .open_compat import open_compat, read_compat
from .file_not_found_error import FileNotFoundError
from .unicode import unicode_from_os
from .clear_directory import clear_directory, unlink_or_delete_directory, is_directory_symlink
from .cache import clear_cache, set_cache, get_cache, merge_cache_under_settings, set_cache_under_settings
from .versions import version_comparable, version_sort
from .downloaders.background_downloader import BackgroundDownloader
from .downloaders.downloader_exception import DownloaderException
from .providers.provider_exception import ProviderException
from .clients.client_exception import ClientException
from .download_manager import downloader
from .providers.release_selector import filter_releases, is_compatible_version
from .upgraders.git_upgrader import GitUpgrader
from .upgraders.hg_upgrader import HgUpgrader
from .package_io import read_package_file, package_file_exists
from .providers import CHANNEL_PROVIDERS, REPOSITORY_PROVIDERS
from .settings import pc_settings_filename, load_list_setting, save_list_setting
from . import loader, text
from . import __version__


DEFAULT_CHANNEL = 'https://packagecontrol.io/channel_v3.json'
OLD_DEFAULT_CHANNELS = set([
    'https://packagecontrol.io/channel.json',
    'https://sublime.wbond.net/channel.json',
    'https://sublime.wbond.net/repositories.json'
])


class PackageManager():

    """
    Allows downloading, creating, installing, upgrading, and deleting packages

    Delegates metadata retrieval to the CHANNEL_PROVIDERS classes.
    Uses VcsUpgrader-based classes for handling git and hg repositories in the
    Packages folder. Downloader classes are utilized to fetch contents of URLs.

    Also handles displaying package messaging, and sending usage information to
    the usage server.
    """

    def __init__(self):
        # Here we manually copy the settings since sublime doesn't like
        # code accessing settings from threads
        self.settings = {}
        settings = sublime.load_settings(pc_settings_filename())
        setting_names = [
            'auto_upgrade',
            'auto_upgrade_frequency',
            'auto_upgrade_ignore',
            'cache_length',
            'channels',
            'debug',
            'dirs_to_ignore',
            'downloader_precedence',
            'files_to_ignore',
            'files_to_include',
            'git_binary',
            'git_update_command',
            'hg_binary',
            'hg_update_command',
            'http_cache',
            'http_cache_length',
            'http_proxy',
            'https_proxy',
            'ignore_vcs_packages',
            'install_prereleases',
            'package_destination',
            'package_name_map',
            'package_profiles',
            'proxy_password',
            'proxy_username',
            'renamed_packages',
            'repositories',
            'submit_url',
            'submit_usage',
            'timeout',
            'user_agent'
        ]
        for setting in setting_names:
            if settings.get(setting) is None:
                continue
            self.settings[setting] = settings.get(setting)

        # https_proxy will inherit from http_proxy unless it is set to a
        # string value or false
        no_https_proxy = self.settings.get('https_proxy') in ["", None]
        if no_https_proxy and self.settings.get('http_proxy'):
            self.settings['https_proxy'] = self.settings.get('http_proxy')
        if self.settings.get('https_proxy') is False:
            self.settings['https_proxy'] = ''

        # We cache these to prevent IPC calls between plugin_host and the main
        # Sublime Text executable
        self.settings['platform'] = sublime.platform()
        self.settings['arch'] = sublime.arch()
        self.settings['version'] = int(sublime.version())
        self.settings['packages_path'] = sublime.packages_path()
        self.settings['installed_packages_path'] = sublime.installed_packages_path()

        # Use the cache to see if settings have changed since the last
        # time the package manager was created, and clearing any cached
        # values if they have.
        previous_settings = get_cache('filtered_settings', {})

        # Reduce the settings down to exclude channel info since that will
        # make the settings always different
        filtered_settings = self.settings.copy()
        for key in ['repositories', 'channels', 'package_name_map', 'cache']:
            if key in filtered_settings:
                del filtered_settings[key]

        if filtered_settings != previous_settings and previous_settings != {}:
            console_write(
                u'''
                Settings change detected, clearing cache
                '''
            )
            clear_cache()
        set_cache('filtered_settings', filtered_settings)

    def get_metadata(self, package, is_dependency=False):
        """
        Returns the package metadata for an installed package

        :param package:
            The name of the package

        :param is_dependency:
            If the metadata is for a dependency

        :return:
            A dict with the keys:
                version
                url
                description
            or an empty dict on error
        """

        metadata_filename = 'package-metadata.json'
        if is_dependency:
            metadata_filename = 'dependency-metadata.json'

        if package_file_exists(package, metadata_filename):
            metadata_json = read_package_file(package, metadata_filename)
            if metadata_json:
                try:
                    return json.loads(metadata_json)
                except (ValueError):
                    console_write(
                        u'''
                        An error occurred while trying to parse the package
                        metadata for %s.
                        ''',
                        package
                    )

        return {}

    def get_dependencies(self, package):
        """
        Returns a list of dependencies for the specified package on the
        current machine

        :param package:
            The name of the package

        :return:
            A list of dependency names
        """

        if package_file_exists(package, 'dependencies.json'):
            dep_info_json = read_package_file(package, 'dependencies.json')
            if dep_info_json:
                try:
                    return self.select_dependencies(json.loads(dep_info_json))
                except (ValueError):
                    console_write(
                        u'''
                        An error occurred while trying to parse the
                        dependencies.json for %s.
                        ''',
                        package
                    )

        metadata = self.get_metadata(package)
        if metadata:
            return metadata.get('dependencies', [])

        return []

    def get_dependency_priority_code(self, dependency):
        """
        Returns the priority and loader code for a dependency that is already
        on disk.

        This is primarily only useful when a package author has a
        dependency they are developing locally and Package Control needs to
        know how to set up a loader for it.

        :param dependency:
            A unicode string of the dependency to get the info for

        :return:
            A 2-element tuple of unicode strings (priority, python code). Return
            value will be (None, None) if the dependency was not found on disk.
        """

        dependency_path = self.get_package_dir(dependency)
        if not os.path.exists(dependency_path):
            return (None, None)

        dependencies = self.list_available_dependencies()

        hidden_file_path = os.path.join(dependency_path, '.sublime-dependency')
        loader_py_path = os.path.join(dependency_path, 'loader.py')
        loader_code_path = os.path.join(dependency_path, 'loader.code')

        priority = None

        if dependency in dependencies:
            priority = dependencies[dependency].get('load_order')

        # Look in the .sublime-dependency file to see where in the dependency
        # load order this dependency should be installed
        elif os.path.exists(hidden_file_path):
            with open(hidden_file_path, 'rb') as f:
                data = f.read().decode('utf-8').strip()
                if data.isdigit():
                    priority = data
                    if len(priority) == 1:
                        priority = '0' + priority

        if priority is None:
            priority = '50'

        code = None
        is_py_loader = os.path.exists(loader_py_path)
        is_code_loader = os.path.exists(loader_code_path)
        if is_py_loader or is_code_loader:
            loader_path = loader_code_path if is_code_loader else loader_py_path
            with open(loader_path, 'rb') as f:
                code = f.read().decode('utf-8')

        return (priority, code)

    def _is_git_package(self, package):
        """
        :param package:
            The package name

        :return:
            If the package is installed via git
        """

        git_dir = os.path.join(self.get_package_dir(package), '.git')
        return os.path.exists(git_dir) and (os.path.isdir(git_dir) or os.path.isfile(git_dir))

    def _is_hg_package(self, package):
        """
        :param package:
            The package name

        :return:
            If the package is installed via hg
        """

        hg_dir = os.path.join(self.get_package_dir(package), '.hg')
        return os.path.exists(hg_dir) and os.path.isdir(hg_dir)

    def is_vcs_package(self, package):
        """
        If the package is installed via git or hg

        :param package:
            The package to check

        :return:
            bool
        """

        return self._is_git_package(package) or self._is_hg_package(package)

    def get_version(self, package):
        """
        Determines the current version for a package

        :param package:
            The package name
        """

        version = self.get_metadata(package).get('version')

        if version:
            return version

        if self.is_vcs_package(package):
            upgrader = self.instantiate_upgrader(package)
            version = upgrader.latest_commit()
            if version:
                return '%s commit %s' % (upgrader.cli_name, version)

        return 'unknown version'

    def instantiate_upgrader(self, package):
        """
        Creates an HgUpgrader or GitUpgrader object to run operations on a VCS-
        based package

        :param package:
            The name of the package

        :return:
            GitUpgrader, HgUpgrader or None
        """

        if self._is_git_package(package):
            return GitUpgrader(
                self.settings['git_binary'],
                self.settings['git_update_command'],
                self.get_package_dir(package),
                self.settings['cache_length'],
                self.settings['debug']
            )

        if self._is_hg_package(package):
            return HgUpgrader(
                self.settings['hg_binary'],
                self.settings['hg_update_command'],
                self.get_package_dir(package),
                self.settings['cache_length'],
                self.settings['debug']
            )

        return None

    def select_dependencies(self, dependency_info):
        """
        Takes the a dict from a dependencies.json file and returns the
        dependency names that are applicable to the current machine

        :param dependency_info:
            A dict from a dependencies.json file

        :return:
            A list of dependency names
        """

        platform_selectors = [
            self.settings['platform'] + '-' + self.settings['arch'],
            self.settings['platform'],
            '*'
        ]

        for platform_selector in platform_selectors:
            if platform_selector not in dependency_info:
                continue

            platform_dependency = dependency_info[platform_selector]
            versions = platform_dependency.keys()

            # Sorting reverse will give us >, < then *
            for version_selector in sorted(versions, reverse=True):
                if not is_compatible_version(version_selector):
                    continue
                return platform_dependency[version_selector]

        # If there were no matches in the info, but there also weren't any
        # errors, then it just means there are not dependencies for this machine
        return []

    def list_repositories(self):
        """
        Returns a master list of all repositories pulled from all sources

        These repositories come from the channels specified in the
        "channels" setting, plus any repositories listed in the
        "repositories" setting.

        :return:
            A list of all available repositories
        """

        cache_ttl = self.settings.get('cache_length')

        repositories = self.settings.get('repositories')[:]
        channels = self.settings.get('channels')

        # Update any old default channel URLs users have in their config
        updated_channels = []
        found_default = False
        for channel in channels:
            if re.match(r'https?://([^.]+\.)*package-control\.io', channel):
                console_write('Removed malicious channel %s' % channel)
                continue
            if channel in OLD_DEFAULT_CHANNELS:
                if not found_default:
                    updated_channels.append(DEFAULT_CHANNEL)
                    found_default = True
                continue
            updated_channels.append(channel)

        for channel in updated_channels:
            channel = channel.strip()

            # Caches various info from channels for performance
            cache_key = channel + '.repositories'
            channel_repositories = get_cache(cache_key)

            merge_cache_under_settings(self, 'package_name_map', channel)
            merge_cache_under_settings(self, 'renamed_packages', channel)
            merge_cache_under_settings(self, 'unavailable_packages', channel, list_=True)
            merge_cache_under_settings(self, 'unavailable_dependencies', channel, list_=True)

            # If any of the info was not retrieved from the cache, we need to
            # grab the channel to get it
            if channel_repositories is None:

                for provider_class in CHANNEL_PROVIDERS:
                    if provider_class.match_url(channel):
                        provider = provider_class(channel, self.settings)
                        break

                try:
                    channel_repositories = provider.get_repositories()
                    set_cache(cache_key, channel_repositories, cache_ttl)

                    unavailable_packages = []
                    unavailable_dependencies = []

                    for repo in channel_repositories:
                        original_packages = provider.get_packages(repo)
                        filtered_packages = {}
                        for package in original_packages:
                            info = original_packages[package]
                            info['releases'] = filter_releases(package, self.settings, info['releases'])
                            if info['releases']:
                                filtered_packages[package] = info
                            else:
                                unavailable_packages.append(package)
                        packages_cache_key = repo + '.packages'
                        set_cache(packages_cache_key, filtered_packages, cache_ttl)

                        original_dependencies = provider.get_dependencies(repo)
                        filtered_dependencies = {}
                        for dependency in original_dependencies:
                            info = original_dependencies[dependency]
                            info['releases'] = filter_releases(dependency, self.settings, info['releases'])
                            if info['releases']:
                                filtered_dependencies[dependency] = info
                            else:
                                unavailable_dependencies.append(dependency)
                        dependencies_cache_key = repo + '.dependencies'
                        set_cache(dependencies_cache_key, filtered_dependencies, cache_ttl)

                    # Have the local name map override the one from the channel
                    name_map = provider.get_name_map()
                    set_cache_under_settings(self, 'package_name_map', channel, name_map, cache_ttl)

                    renamed_packages = provider.get_renamed_packages()
                    set_cache_under_settings(self, 'renamed_packages', channel, renamed_packages, cache_ttl)

                    set_cache_under_settings(
                        self,
                        'unavailable_packages',
                        channel,
                        unavailable_packages,
                        cache_ttl,
                        list_=True
                    )
                    set_cache_under_settings(
                        self,
                        'unavailable_dependencies',
                        channel,
                        unavailable_dependencies,
                        cache_ttl,
                        list_=True
                    )

                except (DownloaderException, ClientException, ProviderException) as e:
                    console_write(e)
                    continue

            repositories.extend(channel_repositories)
        return [repo.strip() for repo in repositories]

    def _list_available(self):
        """
        Returns a master list of every available package and dependency from all sources

        :return:
            A 2-element tuple, in the format:
            (
                {
                    'Package Name': {
                        # Package details - see example-repository.json for format
                    },
                    ...
                },
                {
                    'Dependency Name': {
                        # Dependency details - see example-repository.json for format
                    },
                    ...
                }
            )
        """

        if self.settings.get('debug'):
            console_write(
                u'''
                Fetching list of available packages and dependencies
                  Platform: %s-%s
                  Sublime Text Version: %s
                  Package Control Version: %s
                ''',
                (
                    self.settings['platform'],
                    self.settings['arch'],
                    self.settings['version'],
                    __version__
                )
            )

        cache_ttl = self.settings.get('cache_length')
        repositories = self.list_repositories()
        packages = {}
        dependencies = {}
        bg_downloaders = {}
        active = []
        repos_to_download = []
        name_map = self.settings.get('package_name_map', {})

        # Repositories are run in reverse order so that the ones first
        # on the list will overwrite those last on the list
        for repo in repositories[::-1]:
            if re.match(r'https?://([^.]+\.)*package-control\.io', repo):
                console_write('Removed malicious repository %s' % repo)
                continue

            cache_key = repo + '.packages'
            repository_packages = get_cache(cache_key)

            if repository_packages is not None:
                packages.update(repository_packages)

                cache_key = repo + '.dependencies'
                repository_dependencies = get_cache(cache_key)
                dependencies.update(repository_dependencies)

            else:
                domain = urlparse(repo).hostname
                if domain not in bg_downloaders:
                    bg_downloaders[domain] = BackgroundDownloader(
                        self.settings, REPOSITORY_PROVIDERS)
                bg_downloaders[domain].add_url(repo)
                repos_to_download.append(repo)

        for bg_downloader in list(bg_downloaders.values()):
            bg_downloader.start()
            active.append(bg_downloader)

        # Wait for all of the downloaders to finish
        while active:
            bg_downloader = active.pop()
            bg_downloader.join()

        # Grabs the results and stuff it all in the cache
        for repo in repos_to_download:
            domain = urlparse(repo).hostname
            bg_downloader = bg_downloaders[domain]
            provider = bg_downloader.get_provider(repo)
            if not provider:
                continue

            unavailable_packages = []
            unavailable_dependencies = []

            # Allow name mapping of packages for schema version < 2.0
            repository_packages = {}
            for name, info in provider.get_packages():
                name = name_map.get(name, name)
                info['name'] = name
                info['releases'] = filter_releases(name, self.settings, info['releases'])
                if info['releases']:
                    repository_packages[name] = info
                else:
                    unavailable_packages.append(name)

            repository_dependencies = {}
            for name, info in provider.get_dependencies():
                info['releases'] = filter_releases(name, self.settings, info['releases'])
                if info['releases']:
                    repository_dependencies[name] = info
                else:
                    unavailable_dependencies.append(name)

            # Display errors we encountered while fetching package info
            for url, exception in provider.get_failed_sources():
                console_write(exception)
            for name, exception in provider.get_broken_packages():
                console_write(exception)
            for name, exception in provider.get_broken_dependencies():
                console_write(exception)

            cache_key = repo + '.packages'
            set_cache(cache_key, repository_packages, cache_ttl)
            packages.update(repository_packages)

            cache_key = repo + '.dependencies'
            set_cache(cache_key, repository_dependencies, cache_ttl)
            dependencies.update(repository_dependencies)

            renamed_packages = provider.get_renamed_packages()
            set_cache_under_settings(self, 'renamed_packages', repo, renamed_packages, cache_ttl)

            set_cache_under_settings(
                self,
                'unavailable_packages',
                repo,
                unavailable_packages,
                cache_ttl,
                list_=True
            )
            set_cache_under_settings(
                self,
                'unavailable_dependencies',
                repo,
                unavailable_dependencies,
                cache_ttl,
                list_=True
            )

        return (packages, dependencies)

    def list_available_dependencies(self):
        """
        Returns a master list of every available dependency from all sources

        :return:
            A dict in the format:
            {
                'Dependency Name': {
                    # Dependency details - see example-repository.json for format
                },
                ...
            }
        """

        return self._list_available()[1]

    def list_available_packages(self):
        """
        Returns a master list of every available package from all sources

        :return:
            A dict in the format:
            {
                'Package Name': {
                    # Package details - see example-repository.json for format
                },
                ...
            }
        """

        return self._list_available()[0]

    def list_packages(self, unpacked_only=False):
        """
        :param unpacked_only:
            Only list packages that are not inside of .sublime-package files

        :return: A list of all installed, non-default, non-dependency, package names
        """

        packages = self._list_visible_dirs(self.settings['packages_path'])

        if self.settings['version'] > 3000 and unpacked_only is False:
            packages |= self._list_sublime_package_files(self.settings['installed_packages_path'])

        packages -= set(self.list_default_packages())
        packages -= set(self.list_dependencies())
        packages -= set(['User', 'Default'])
        return sorted(packages, key=lambda s: s.lower())

    def list_dependencies(self):
        """
        :return: A list of all installed dependency names
        """

        output = []

        # This is seeded since it is in a .sublime-package with ST3
        if sys.version_info >= (3,):
            output.append('0_package_control_loader')

        for name in self._list_visible_dirs(self.settings['packages_path']):
            if not self._is_dependency(name):
                continue
            output.append(name)

        return sorted(output, key=lambda s: s.lower())

    def list_unloaded_dependencies(self):
        """
        :return:
            A list of the names of dependencies in the Packages/ folder that
            are not currently being loaded
        """

        output = []
        for name in self._list_visible_dirs(self.settings['packages_path']):
            hidden_file_path = os.path.join(self.settings['packages_path'], name, '.sublime-dependency')
            if not os.path.exists(hidden_file_path):
                continue
            if not loader.exists(name):
                output.append(name)
        return output

    def list_all_packages(self):
        """
        Lists all packages on the machine

        :return:
            A list of all installed package names, including default packages
        """

        packages = self.list_default_packages() + self.list_packages()
        return sorted(packages, key=lambda s: s.lower())

    def list_default_packages(self):
        """ :return: A list of all default package names"""

        if self.settings['version'] > 3000:
            app_dir = os.path.dirname(sublime.executable_path())
            packages = self._list_sublime_package_files(os.path.join(app_dir, 'Packages'))

        else:
            config_dir = os.path.dirname(self.settings['packages_path'])

            pristine_dir = os.path.join(config_dir, 'Pristine Packages')
            pristine_files = self._list_sublime_package_files(pristine_dir)

            installed_dir = self.settings['installed_packages_path']
            installed_files = self._list_sublime_package_files(installed_dir)

            packages = pristine_files - installed_files

        packages -= set(['User', 'Default'])
        return sorted(packages, key=lambda s: s.lower())

    def _list_visible_dirs(self, path):
        """
        Return a set of directories in the folder specified that are not
        hidden and are not marked to be removed

        :param path:
            The folder to list the directories inside of

        :return:
            A set of directory names
        """

        output = set()
        for filename in os.listdir(path):
            if filename[0] == '.':
                continue
            file_path = os.path.join(path, filename)
            if not os.path.isdir(file_path):
                continue
            # Don't include a dir if it is going to be cleaned up
            if os.path.exists(os.path.join(file_path, 'package-control.cleanup')):
                continue
            output.add(filename)
        return output

    def _list_sublime_package_files(self, path):
        """
        Return a set of all .sublime-package files in a folder

        :param path:
            The directory to look in for .sublime-package files

        :return:
            A set of the package names - i.e. with the .sublime-package suffix removed
        """

        output = set()
        if not os.path.exists(path):
            return output
        for filename in os.listdir(path):
            if not re.search(r'\.sublime-package$', filename):
                continue
            output.add(filename.replace('.sublime-package', ''))
        return output

    def _is_dependency(self, name):
        """
        Checks if a package specified is a dependency

        :param name:
            The name of the package to check if it is a dependency

        :return:
            Bool, if the package is a dependency
        """

        metadata_path = os.path.join(self.settings['packages_path'], name, 'dependency-metadata.json')
        hidden_path = os.path.join(self.settings['packages_path'], name, '.sublime-dependency')
        return os.path.exists(metadata_path) or os.path.exists(hidden_path)

    def find_required_dependencies(self, ignore_package=None):
        """
        Find all of the dependencies required by the installed packages,
        ignoring the specified package.

        :param ignore_package:
            The package to ignore when enumerating dependencies

        :return:
            A list of the dependencies required by the installed packages
        """

        output = ['0_package_control_loader']

        for package in self.list_packages():
            if package == ignore_package:
                continue
            output.extend(self.get_dependencies(package))

        # Consider any folder with a .sublime-dependency file that does not
        # have a dependency-metadata.json file to be a dependency that was
        # hand-installed by a developer, and thus "required"
        for name in self._list_visible_dirs(self.settings['packages_path']):
            metadata_path = os.path.join(self.settings['packages_path'], name, 'dependency-metadata.json')
            hidden_path = os.path.join(self.settings['packages_path'], name, '.sublime-dependency')
            metadata_exists = os.path.exists(metadata_path)
            hidden_exists = os.path.exists(hidden_path)
            if metadata_exists or not hidden_exists:
                continue
            output.append(name)

        output = list(set(output))
        return sorted(output, key=lambda s: s.lower())

    def get_package_dir(self, package):
        """:return: The full filesystem path to the package directory"""

        return os.path.join(self.settings['packages_path'], package)

    def get_mapped_name(self, package):
        """:return: The name of the package after passing through mapping rules"""

        return self.settings.get('package_name_map', {}).get(package, package)

    def create_package(self, package_name, package_destination, profile=None):
        """
        Creates a .sublime-package file from the running Packages directory

        :param package_name:
            The package to create a .sublime-package file for

        :param package_destination:
            The full filesystem path of the directory to save the new
            .sublime-package file in.

        :param profile:
            If None, the "dirs_to_ignore", "files_to_ignore", "files_to_include"
            and "package_destination" settings will be used when creating the
            package. If a string, will look in the "package_profiles" setting
            and use the profile name to select a sub-dictionary which may
            contain all of the ignore/include settings.

        :return: bool if the package file was successfully created
        """

        package_dir = self.get_package_dir(package_name)

        if not os.path.exists(package_dir):
            show_error(
                u'''
                The folder for the package name specified, %s,
                does not exists in %s
                ''',
                (package_name, self.settings['packages_path'])
            )
            return False

        package_filename = package_name + '.sublime-package'
        package_path = os.path.join(package_destination, package_filename)

        if not os.path.exists(self.settings['installed_packages_path']):
            os.mkdir(self.settings['installed_packages_path'])

        if os.path.exists(package_path):
            os.remove(package_path)

        try:
            package_file = zipfile.ZipFile(package_path, "w", compression=zipfile.ZIP_DEFLATED)
        except (OSError, IOError) as e:
            show_error(
                u'''
                An error occurred creating the package file %s in %s.

                %s
                ''',
                (package_filename, package_destination, unicode_from_os(e))
            )
            return False

        if self.settings['version'] >= 3000:
            compileall.compile_dir(package_dir, quiet=True, legacy=True, optimize=2)

        if profile:
            profile_settings = self.settings.get('package_profiles').get(profile)

        def get_profile_setting(setting, default):
            if profile:
                profile_value = profile_settings.get(setting)
                if profile_value is not None:
                    return profile_value
            return self.settings.get(setting, default)

        dirs_to_ignore = get_profile_setting('dirs_to_ignore', [])
        files_to_ignore = get_profile_setting('files_to_ignore', [])
        files_to_include = get_profile_setting('files_to_include', [])

        slash = '\\' if os.name == 'nt' else '/'
        trailing_package_dir = package_dir + slash if package_dir[-1] != slash else package_dir
        package_dir_regex = re.compile('^' + re.escape(trailing_package_dir))
        for root, dirs, files in os.walk(package_dir):
            # add "dir" to "paths" list if "dir" is not in "dirs_to_ignore"
            dirs[:] = [x for x in dirs if x not in dirs_to_ignore]
            paths = dirs
            paths.extend(files)
            for path in paths:
                full_path = os.path.join(root, path)
                relative_path = re.sub(package_dir_regex, '', full_path)

                ignore_matches = [fnmatch(relative_path, p) for p in files_to_ignore]
                include_matches = [fnmatch(relative_path, p) for p in files_to_include]
                if any(ignore_matches) and not any(include_matches):
                    continue

                if os.path.isdir(full_path):
                    continue
                package_file.write(full_path, relative_path)

        package_file.close()

        return True

    def install_package(self, package_name, is_dependency=False):
        """
        Downloads and installs (or upgrades) a package

        Uses the self.list_available_packages() method to determine where to
        retrieve the package file from.

        The install process consists of:

        1. Finding the package
        2. Downloading the .sublime-package/.zip file
        3. Extracting the package file
        4. Showing install/upgrade messaging
        5. Submitting usage info
        6. Recording that the package is installed

        :param package_name:
            The package to download and install

        :param is_dependency:
            If the package is a dependency

        :return: bool if the package was successfully installed or None
                 if the package needs to be cleaned up on the next restart
                 and should not be reenabled
        """

        if is_dependency:
            packages = self.list_available_dependencies()
        else:
            packages = self.list_available_packages()

        is_available = package_name in list(packages.keys())

        unavailable_key = 'unavailable_packages'
        if is_dependency:
            unavailable_key = 'unavailable_dependencies'
        is_unavailable = package_name in self.settings.get(unavailable_key, [])

        package_type = 'package'
        if is_dependency:
            package_type = 'dependency'

        if is_unavailable and not is_available:
            console_write(
                u'''
                The %s "%s" is either not available on this platform or for
                this version of Sublime Text
                ''',
                (package_type, package_name)
            )
            # If a dependency is not available on this machine, that means it
            # is not needed
            if is_dependency:
                return True
            return False

        if not is_available:
            message = u"The %s '%s' is not available"
            params = (package_type, package_name)
            if is_dependency:
                console_write(message, params)
            else:
                show_error(message, params)
            return False

        release = packages[package_name]['releases'][0]

        have_installed_dependencies = False
        if not is_dependency:
            dependencies = release.get('dependencies', [])
            if dependencies:
                if not self.install_dependencies(dependencies):
                    return False
                have_installed_dependencies = True

        url = release['url']
        package_filename = package_name + '.sublime-package'

        tmp_dir = tempfile.mkdtemp(u'')

        try:
            # This is refers to the zipfile later on, so we define it here so we can
            # close the zip file if set during the finally clause
            package_zip = None

            tmp_package_path = os.path.join(tmp_dir, package_filename)

            unpacked_package_dir = self.get_package_dir(package_name)
            package_path = os.path.join(self.settings['installed_packages_path'], package_filename)
            pristine_package_path = os.path.join(
                os.path.dirname(self.settings['packages_path']),
                'Pristine Packages',
                package_filename
            )

            if self.is_vcs_package(package_name):
                upgrader = self.instantiate_upgrader(package_name)
                to_ignore = self.settings.get('ignore_vcs_packages')

                if to_ignore is True:
                    show_error(
                        u'''
                        Skipping %s package %s since the setting
                        "ignore_vcs_packages" is set to true
                        ''',
                        (upgrader.cli_name, package_name)
                    )
                    return False

                if isinstance(to_ignore, list) and package_name in to_ignore:
                    show_error(
                        u'''
                        Skipping %s package %s since it is listed in the
                        "ignore_vcs_packages" setting
                        ''',
                        (upgrader.cli_name, package_name)
                    )
                    return False

                result = upgrader.run()

                if result is True and is_dependency:
                    load_order, loader_code = self.get_dependency_priority_code(package_name)
                    loader.add_or_update(load_order, package_name, loader_code)

                return result

            old_version = self.get_metadata(package_name, is_dependency=is_dependency).get('version')
            is_upgrade = old_version is not None

            # Download the sublime-package or zip file
            try:
                with downloader(url, self.settings) as manager:
                    package_bytes = manager.fetch(url, 'Error downloading package.')
            except (DownloaderException) as e:
                console_write(e)
                show_error(
                    u'''
                    Unable to download %s. Please view the console for
                    more details.
                    ''',
                    package_name
                )
                return False

            with open_compat(tmp_package_path, "wb") as package_file:
                package_file.write(package_bytes)

            # Try to open it as a zip file
            try:
                package_zip = zipfile.ZipFile(tmp_package_path, 'r')
            except (zipfile.BadZipfile):
                show_error(
                    u'''
                    An error occurred while trying to unzip the package file
                    for %s. Please try installing the package again.
                    ''',
                    package_name
                )
                return False

            # Scan through the root level of the zip file to gather some info
            root_level_paths = []
            last_path = None
            for path in package_zip.namelist():
                try:
                    if not isinstance(path, str_cls):
                        path = path.decode('utf-8', 'strict')
                except (UnicodeDecodeError):
                    console_write(
                        u'''
                        One or more of the zip file entries in %s is not
                        encoded using UTF-8, aborting
                        ''',
                        package_name
                    )
                    return False

                last_path = path

                if path.find('/') in [len(path) - 1, -1]:
                    root_level_paths.append(path)
                # Make sure there are no paths that look like security vulnerabilities
                if path[0] == '/' or path.find('../') != -1 or path.find('..\\') != -1:
                    show_error(
                        u'''
                        The package specified, %s, contains files outside of
                        the package dir and cannot be safely installed.
                        ''',
                        package_name
                    )
                    return False

            if last_path and len(root_level_paths) == 0:
                root_level_paths.append(last_path[0:last_path.find('/') + 1])

            # If there is only a single directory at the top leve, the file
            # is most likely a zip from BitBucket or GitHub and we need
            # to skip the top-level dir when extracting
            skip_root_dir = len(root_level_paths) == 1 and \
                root_level_paths[0].endswith('/')

            dependencies_path = 'dependencies.json'
            no_package_file_zip_path = '.no-sublime-package'
            if skip_root_dir:
                dependencies_path = root_level_paths[0] + dependencies_path
                no_package_file_zip_path = root_level_paths[0] + no_package_file_zip_path

            # If we should extract unpacked or as a .sublime-package file
            unpack = True

            # By default, ST3 prefers .sublime-package files since this allows
            # overriding files in the Packages/{package_name}/ folder
            if self.settings['version'] >= 3000:
                unpack = False

            # If the package maintainer doesn't want a .sublime-package
            try:
                package_zip.getinfo(no_package_file_zip_path)
                unpack = True
            except (KeyError):
                pass

            # Dependencies are always unpacked. If it doesn't need to be
            # unpacked, it probably should just be part of a package instead
            # of being split out.
            if is_dependency:
                unpack = True

            # If dependencies were not in the channel, try the package
            if not is_dependency and not have_installed_dependencies:
                try:
                    dep_info_json = package_zip.read(dependencies_path)
                    try:
                        dep_info = json.loads(dep_info_json.decode('utf-8'))
                    except (ValueError):
                        console_write(
                            u'''
                            An error occurred while trying to parse the
                            dependencies.json for %s.
                            ''',
                            package_name
                        )
                        return False

                    dependencies = self.select_dependencies(dep_info)
                    if not self.install_dependencies(dependencies):
                        return False

                except (KeyError):
                    pass

            metadata_filename = 'package-metadata.json'
            if is_dependency:
                metadata_filename = 'dependency-metadata.json'

            # If we already have a package-metadata.json file in
            # Packages/{package_name}/, but the package no longer contains
            # a .no-sublime-package file, then we want to clear the unpacked
            # dir and install as a .sublime-package file. Since we are only
            # clearing if a package-metadata.json file exists, we should never
            # accidentally delete a user's customizations. However, we still
            # create a backup just in case.
            unpacked_metadata_file = os.path.join(unpacked_package_dir, metadata_filename)
            if os.path.exists(unpacked_metadata_file) and not unpack:
                self.backup_package_dir(package_name)
                if is_directory_symlink(unpacked_package_dir):
                    unlink_or_delete_directory(unpacked_package_dir)
                elif not clear_directory(unpacked_package_dir):
                    # If deleting failed, queue the package to upgrade upon next start
                    # where it will be disabled
                    reinstall_file = os.path.join(unpacked_package_dir, 'package-control.reinstall')
                    open_compat(reinstall_file, 'w').close()

                    # Don't delete the metadata file, that way we have it
                    # when the reinstall happens, and the appropriate
                    # usage info can be sent back to the server
                    clear_directory(unpacked_package_dir, [reinstall_file, unpacked_metadata_file])

                    show_error(
                        u'''
                        An error occurred while trying to upgrade %s. Please
                        restart Sublime Text to finish the upgrade.
                        ''',
                        package_name
                    )
                    return None
                else:
                    unlink_or_delete_directory(unpacked_package_dir)

            # If we determined it should be unpacked, we extract directly
            # into the Packages/{package_name}/ folder
            if unpack:
                self.backup_package_dir(package_name)
                package_dir = unpacked_package_dir

            # Otherwise we go into a temp dir since we will be creating a
            # new .sublime-package file later
            else:
                tmp_working_dir = os.path.join(tmp_dir, 'working')
                os.mkdir(tmp_working_dir)
                package_dir = tmp_working_dir

            package_metadata_file = os.path.join(package_dir, metadata_filename)

            if not os.path.exists(package_dir):
                os.mkdir(package_dir)

            os.chdir(package_dir)

            # Look for special loader code for dependencies
            loader_code = None

            # Here we don't use .extractall() since it was having issues on OS X
            overwrite_failed = False
            extracted_paths = set()
            for info in package_zip.infolist():
                path = info.filename
                dest = path

                try:
                    if not isinstance(dest, str_cls):
                        dest = dest.decode('utf-8', 'strict')
                except (UnicodeDecodeError):
                    console_write(
                        u'''
                        One or more of the zip file entries in %s is not
                        encoded using UTF-8, aborting
                        ''',
                        package_name
                    )
                    return False

                if os.name == 'nt':
                    regex = r':|\*|\?|"|<|>|\|'
                    if re.search(regex, dest) is not None:
                        console_write(
                            u'''
                            Skipping file from package named %s due to an
                            invalid filename
                            ''',
                            package_name
                        )
                        continue

                # If there was only a single directory in the package, we remove
                # that folder name from the paths as we extract entries
                if skip_root_dir:
                    dest = dest[len(root_level_paths[0]):]

                if os.name == 'nt':
                    dest = dest.replace('/', '\\')
                else:
                    dest = dest.replace('\\', '/')

                # loader.py is included for backwards compatibility. New code
                # should use loader.code with Python inside of it. We no longer
                # use loader.py since we can't have any files ending in .py in
                # the root of a package, otherwise Sublime Text loads it as a
                # plugin and then the dependency path added to sys.path and the
                # package path loaded by Sublime Text conflict and there will be
                # errors when Sublime Text tries to initialize plugins. By using
                # loader.code, developers can git clone a dependency into their
                # Packages folder without issue.
                if is_dependency and dest in set(['loader.code', 'loader.py']):
                    loader_code = package_zip.read(path).decode('utf-8')
                    if dest == 'loader.py':
                        continue

                dest = os.path.join(package_dir, dest)

                def add_extracted_dirs(dir_):
                    while dir_ not in extracted_paths:
                        extracted_paths.add(dir_)
                        dir_ = os.path.dirname(dir_)
                        if dir_ == package_dir:
                            break

                if path.endswith('/'):
                    if not os.path.exists(dest):
                        os.makedirs(dest)
                    add_extracted_dirs(dest)
                else:
                    dest_dir = os.path.dirname(dest)
                    if not os.path.exists(dest_dir):
                        os.makedirs(dest_dir)
                    add_extracted_dirs(dest_dir)
                    extracted_paths.add(dest)
                    try:
                        with open_compat(dest, 'wb') as f:
                            f.write(package_zip.read(path))
                    except (IOError) as e:
                        message = unicode_from_os(e)
                        if re.search('[Ee]rrno 13', message):
                            overwrite_failed = True
                            break
                        console_write(
                            u'''
                            Skipping file from package named %s due to an
                            invalid filename
                            ''',
                            package_name
                        )

                    except (UnicodeDecodeError):
                        console_write(
                            u'''
                            Skipping file from package named %s due to an
                            invalid filename
                            ''',
                            package_name
                        )

            package_zip.close()
            package_zip = None

            # If upgrading failed, queue the package to upgrade upon next start
            if overwrite_failed:
                reinstall_file = os.path.join(package_dir, 'package-control.reinstall')
                open_compat(reinstall_file, 'w').close()

                # Don't delete the metadata file, that way we have it
                # when the reinstall happens, and the appropriate
                # usage info can be sent back to the server.
                # No need to handle symlink at this stage it was already removed
                # and we are not working with symlink here anymore.
                clear_directory(package_dir, [reinstall_file, package_metadata_file])

                show_error(
                    u'''
                    An error occurred while trying to upgrade %s. Please restart
                    Sublime Text to finish the upgrade.
                    ''',
                    package_name
                )
                return None

            # Here we clean out any files that were not just overwritten. It is ok
            # if there is an error removing a file. The next time there is an
            # upgrade, it should be cleaned out successfully then.
            # No need to handle symlink at this stage it was already removed
            # and we are not working with symlink here anymore.
            clear_directory(package_dir, extracted_paths)

            new_version = release['version']

            self.print_messages(package_name, package_dir, is_upgrade, old_version, new_version)

            with open_compat(package_metadata_file, 'w') as f:
                if is_dependency:
                    url = packages[package_name]['issues']
                else:
                    url = packages[package_name]['homepage']
                metadata = {
                    "version": new_version,
                    "sublime_text": release['sublime_text'],
                    "platforms": release['platforms'],
                    "url": url,
                    "description": packages[package_name]['description']
                }
                if not is_dependency:
                    metadata['dependencies'] = release.get('dependencies', [])
                json.dump(metadata, f)

            # Submit install and upgrade info
            if is_upgrade:
                params = {
                    'package': package_name,
                    'operation': 'upgrade',
                    'version': new_version,
                    'old_version': old_version
                }
            else:
                params = {
                    'package': package_name,
                    'operation': 'install',
                    'version': new_version
                }
            self.record_usage(params)

            if not is_dependency:
                # Record the install in the settings file so that you can move
                # settings across computers and have the same packages installed
                def save_names():
                    settings = sublime.load_settings(pc_settings_filename())
                    original_names = load_list_setting(settings, 'installed_packages')
                    names = list(original_names)
                    if package_name not in names:
                        names.append(package_name)
                    save_list_setting(settings, pc_settings_filename(), 'installed_packages', names, original_names)
                sublime.set_timeout(save_names, 1)

            else:
                load_order = packages[package_name]['load_order']
                loader.add_or_update(load_order, package_name, loader_code)

            # If we didn't extract directly into the Packages/{package_name}/
            # folder, we need to create a .sublime-package file and install it
            if not unpack:
                try:
                    # Remove the downloaded file since we are going to overwrite it
                    os.remove(tmp_package_path)
                    package_zip = zipfile.ZipFile(tmp_package_path, "w", compression=zipfile.ZIP_DEFLATED)
                except (OSError, IOError) as e:
                    show_error(
                        u'''
                        An error occurred creating the package file %s in %s.

                        %s
                        ''',
                        (package_filename, tmp_dir, unicode_from_os(e))
                    )
                    return False

                package_dir_regex = re.compile('^' + re.escape(package_dir))
                for root, dirs, files in os.walk(package_dir):
                    paths = dirs
                    paths.extend(files)
                    for path in paths:
                        full_path = os.path.join(root, path)
                        relative_path = re.sub(package_dir_regex, '', full_path)
                        if os.path.isdir(full_path):
                            continue
                        package_zip.write(full_path, relative_path)

                package_zip.close()
                package_zip = None

                try:
                    if os.path.exists(package_path):
                        os.remove(package_path)
                    shutil.move(tmp_package_path, package_path)
                except (OSError):
                    new_package_path = package_path.replace('.sublime-package', '.sublime-package-new')
                    shutil.move(tmp_package_path, new_package_path)
                    show_error(
                        u'''
                        An error occurred while trying to upgrade %s. Please restart
                        Sublime Text to finish the upgrade.
                        ''',
                        package_name
                    )
                    return None

            # We have to remove the pristine package too or else Sublime Text 2
            # will silently delete the package
            if os.path.exists(pristine_package_path):
                os.remove(pristine_package_path)

            os.chdir(self.settings['packages_path'])
            return True

        finally:
            # We need to make sure the zipfile is closed to
            # help prevent permissions errors on Windows
            if package_zip:
                package_zip.close()

            # Try to remove the tmp dir after a second to make sure
            # a virus scanner is holding a reference to the zipfile
            # after we close it.
            sublime.set_timeout(lambda: unlink_or_delete_directory(tmp_dir), 1000)

    def install_dependencies(self, dependencies, fail_early=True):
        """
        Ensures a list of dependencies are installed and up-to-date

        :param dependencies:
            A list of dependency names

        :return:
            A boolean indicating if the dependencies are properly installed
        """

        debug = self.settings.get('debug')

        packages = self.list_available_dependencies()

        error = False
        for dependency in dependencies:
            # This is a per-machine dynamically created dependency, so we skip
            if dependency == '0_package_control_loader':
                continue

            # Collect dependency information
            dependency_dir = os.path.join(self.settings['packages_path'], dependency)
            dependency_git_dir = os.path.join(dependency_dir, '.git')
            dependency_hg_dir = os.path.join(dependency_dir, '.hg')
            dependency_metadata = self.get_metadata(dependency, is_dependency=True)

            dependency_releases = packages.get(dependency, {}).get('releases', [])
            dependency_release = dependency_releases[0] if dependency_releases else {}

            installed_version = dependency_metadata.get('version')
            installed_version = version_comparable(installed_version) if installed_version else None
            available_version = dependency_release.get('version')
            available_version = version_comparable(available_version) if available_version else None

            def dependency_write(msg):
                msg = u"The dependency '{dependency}' " + msg
                msg = msg.format(
                    dependency=dependency,
                    installed_version=installed_version,
                    available_version=available_version
                )
                console_write(msg)

            def dependency_write_debug(msg):
                if debug:
                    dependency_write(msg)

            install_dependency = False
            if not os.path.exists(dependency_dir):
                install_dependency = True
                dependency_write(u'is not currently installed; installing...')
            elif os.path.exists(dependency_git_dir):
                dependency_write_debug(u'is installed via git; leaving alone')
            elif os.path.exists(dependency_hg_dir):
                dependency_write_debug(u'is installed via hg; leaving alone')
            elif not dependency_metadata:
                dependency_write_debug(u'appears to be installed, but is missing metadata; leaving alone')
            elif not dependency_releases:
                dependency_write(u'is installed, but there are no available releases; leaving alone')
            elif not available_version:
                dependency_write(
                    u'is installed, but the latest available release '
                    u'could not be determined; leaving alone'
                )
            elif not installed_version:
                install_dependency = True
                dependency_write(
                    u'is installed, but its version is not known; '
                    u'upgrading to latest release {available_version}...'
                )
            elif installed_version < available_version:
                install_dependency = True
                dependency_write(
                    u'is installed, but out of date; upgrading to latest '
                    u'release {available_version} from {installed_version}...'
                )
            else:
                dependency_write_debug(u'is installed and up to date ({installed_version}); leaving alone')

            if install_dependency:
                dependency_result = self.install_package(dependency, True)
                if not dependency_result:
                    dependency_write(u'could not be installed or updated')
                    if fail_early:
                        return False
                    error = True
                else:
                    dependency_write(u'has successfully been installed or updated')

        return not error

    def cleanup_dependencies(self, ignore_package=None, required_dependencies=None):
        """
        Remove all not needed dependencies by the installed packages,
        ignoring the specified package.

        :param ignore_package:
            The package to ignore when enumerating dependencies.
            Not used when required_dependencies is provided.

        :param required_dependencies:
            All required dependencies, for speedup purposes.

        :return:
            Boolean indicating the success of the removals.
        """

        installed_dependencies = self.list_dependencies()
        if not required_dependencies:
            required_dependencies = self.find_required_dependencies(ignore_package)

        orphaned_dependencies = set(installed_dependencies) - set(required_dependencies)
        orphaned_dependencies = sorted(orphaned_dependencies, key=lambda s: s.lower())

        error = False
        for dependency in orphaned_dependencies:
            if self.remove_package(dependency, is_dependency=True):
                console_write(
                    u'''
                    The orphaned dependency %s has been removed
                    ''',
                    dependency
                )
            else:
                error = True

        return not error

    def backup_package_dir(self, package_name):
        """
        Does a full backup of the Packages/{package}/ dir to Backup/

        :param package_name:
            The name of the package to back up

        :return:
            If the backup succeeded
        """

        package_dir = os.path.join(self.settings['packages_path'], package_name)
        if not os.path.exists(package_dir):
            return True

        try:
            backup_dir = os.path.join(os.path.dirname(
                self.settings['packages_path']), 'Backup',
                datetime.datetime.now().strftime('%Y%m%d%H%M%S'))
            if not os.path.exists(backup_dir):
                os.makedirs(backup_dir)
            package_backup_dir = os.path.join(backup_dir, package_name)
            if os.path.exists(package_backup_dir):
                console_write(
                    u'''
                    Backup folder "%s" already exists!
                    ''',
                    package_backup_dir
                )
            shutil.copytree(package_dir, package_backup_dir)
            return True

        except (OSError, IOError) as e:
            show_error(
                u'''
                An error occurred while trying to backup the package directory
                for %s.

                %s
                ''',
                (package_name, unicode_from_os(e))
            )
            try:
                if os.path.exists(package_backup_dir):
                    unlink_or_delete_directory(package_backup_dir)
            except (UnboundLocalError):
                pass  # Exeption occurred before package_backup_dir defined
            return False

    def print_messages(self, package, package_dir, is_upgrade, old_version, new_version):
        """
        Prints out package install and upgrade messages

        The functionality provided by this allows package maintainers to
        show messages to the user when a package is installed, or when
        certain version upgrade occur.

        :param package:
            The name of the package the message is for

        :param package_dir:
            The full filesystem path to the package directory

        :param is_upgrade:
            If the install was actually an upgrade

        :param old_version:
            The string version of the package before the upgrade occurred

        :param new_version:
            The new (string) version of the package
        """

        try:
            messages_file = os.path.join(package_dir, 'messages.json')
            with open_compat(messages_file, 'r') as f:
                message_info = json.loads(read_compat(f))
        except (FileNotFoundError):
            return
        except (ValueError):
            console_write(
                u'''
                Error parsing messages.json for %s
                ''',
                package
            )
            return

        def read_message(message_path):
            with open_compat(message_path, 'r') as f:
                lines = read_compat(f).rstrip().split('\n')
                return '\n' + '\n'.join('  ' + s if s else '' for s in lines)

        output = ''
        if not is_upgrade and message_info.get('install'):
            try:
                install_file = message_info.get('install')
                install_path = os.path.join(package_dir, install_file)
                output += read_message(install_path)
            except (FileNotFoundError):
                console_write(
                    u'''
                    Error opening install message for %s from %s
                    ''',
                    (package, install_file)
                )

        elif is_upgrade and old_version:
            upgrade_messages = list(set(message_info.keys()) - set(['install']))
            upgrade_messages = version_sort(upgrade_messages, reverse=True)
            old_version_cmp = version_comparable(old_version)
            new_version_cmp = version_comparable(new_version)

            for version in upgrade_messages:
                version_cmp = version_comparable(version)
                if version_cmp <= old_version_cmp:
                    break
                # If the package developer sets up release notes for future
                # versions, we don't want to show them for every release
                if version_cmp > new_version_cmp:
                    continue

                try:
                    upgrade_file = message_info.get(version)
                    upgrade_path = os.path.join(package_dir, upgrade_file)
                    output += read_message(upgrade_path)
                except (FileNotFoundError):
                    console_write(
                        u'''
                        Error opening %s message for %s from %s
                        ''',
                        (version, package, upgrade_file)
                    )

        if not output:
            return
        else:
            output = '\n\n%s\n%s\n' % (package, '-' * len(package)) + output

        def print_to_panel():
            window = sublime.active_window()

            views = window.views()
            view = None
            for _view in views:
                if _view.name() == 'Package Control Messages':
                    view = _view
                    break

            if not view:
                view = window.new_file()
                view.set_name('Package Control Messages')
                view.set_scratch(True)
                view.settings().set("word_wrap", True)
                view.settings().set("auto_indent", False)
                view.settings().set("tab_width", 2)
            else:
                view.set_read_only(False)
                if window.active_view() != view:
                    window.focus_view(view)

            def write(string):
                view.run_command('insert', {'characters': string})

            old_sel = list(view.sel())
            old_vpos = view.viewport_position()

            size = view.size()
            view.sel().clear()
            view.sel().add(sublime.Region(size, size))

            if not view.size():
                write(text.format(
                    u'''
                    Package Control Messages
                    ========================
                    '''
                ))
            write(output)

            # Move caret to the new end of the file if it was previously
            if sublime.Region(size, size) == old_sel[-1]:
                old_sel[-1] = sublime.Region(view.size(), view.size())

            view.sel().clear()
            for reg in old_sel:
                view.sel().add(reg)

            view.set_viewport_position(old_vpos, False)
            view.set_read_only(True)

        sublime.set_timeout(print_to_panel, 1)

    def remove_package(self, package_name, is_dependency=False):
        """
        Deletes a package

        The deletion process consists of:

        1. Deleting the directory (or marking it for deletion if deletion fails)
        2. Submitting usage info
        3. Removing the package from the list of installed packages

        :param package_name:
            The package to delete

        :return: bool if the package was successfully deleted or None
                 if the package needs to be cleaned up on the next restart
                 and should not be reenabled
        """

        if not is_dependency:
            installed_packages = self.list_packages()
        else:
            installed_packages = self.list_dependencies()

        package_type = 'package'
        if is_dependency:
            package_type = 'dependency'

        if package_name not in installed_packages:
            show_error(
                u'''
                The %s specified, %s, is not installed
                ''',
                (package_type, package_name)
            )
            return False

        os.chdir(self.settings['packages_path'])

        package_filename = package_name + '.sublime-package'
        installed_package_path = os.path.join(self.settings['installed_packages_path'], package_filename)
        pristine_package_path = os.path.join(
            os.path.dirname(self.settings['packages_path']),
            'Pristine Packages',
            package_filename
        )
        package_dir = self.get_package_dir(package_name)

        version = self.get_metadata(package_name, is_dependency=is_dependency).get('version')

        cleanup_complete = True

        try:
            if os.path.exists(installed_package_path):
                os.remove(installed_package_path)
        except (OSError, IOError):
            cleanup_complete = False

        try:
            if os.path.exists(pristine_package_path):
                os.remove(pristine_package_path)
        except (OSError, IOError) as e:
            show_error(
                u'''
                An error occurred while trying to remove the pristine package
                file for %s.

                %s
                ''',
                (package_name, unicode_from_os(e))
            )
            return False

        if os.path.exists(package_dir):
            # We don't delete the actual package dir immediately due to a bug
            # in sublime_plugin.py
            can_delete_dir = True
            if is_directory_symlink(package_dir):
                # Assuming that deleting symlink won't fail in later step so
                # not having any cleanup handling here
                pass
            elif not clear_directory(package_dir):
                # If there is an error deleting now, we will mark it for
                # cleanup the next time Sublime Text starts
                open_compat(os.path.join(package_dir, 'package-control.cleanup'), 'w').close()
                cleanup_complete = False
                can_delete_dir = False

        params = {
            'package': package_name,
            'operation': 'remove',
            'version': version
        }
        self.record_usage(params)

        if not is_dependency:
            def save_names():
                settings = sublime.load_settings(pc_settings_filename())
                original_names = load_list_setting(settings, 'installed_packages')
                names = list(original_names)
                if package_name in names:
                    names.remove(package_name)
                save_list_setting(settings, pc_settings_filename(), 'installed_packages', names, original_names)
            sublime.set_timeout(save_names, 1)

        if os.path.exists(package_dir) and can_delete_dir:
            unlink_or_delete_directory(package_dir)

        if is_dependency:
            loader.remove(package_name)

        else:
            message = u'The package %s has been removed' % package_name
            if not cleanup_complete:
                message += u' and will be cleaned up on the next restart'
            console_write(message)

            # Remove dependencies that are no longer needed
            self.cleanup_dependencies(package_name)

        return True if cleanup_complete else None

    def record_usage(self, params):
        """
        Submits install, upgrade and delete actions to a usage server

        The usage information is currently displayed on the Package Control
        website at https://packagecontrol.io

        :param params:
            A dict of the information to submit
        """

        if not self.settings.get('submit_usage'):
            return
        params['package_control_version'] = \
            self.get_metadata('Package Control').get('version')
        params['sublime_platform'] = self.settings.get('platform')
        params['sublime_version'] = self.settings.get('version')

        # For Python 2, we need to explicitly encoding the params
        for param in params:
            if isinstance(params[param], str_cls):
                params[param] = params[param].encode('utf-8')

        url = self.settings.get('submit_url') + '?' + urlencode(params)

        try:
            with downloader(url, self.settings) as manager:
                result = manager.fetch(url, 'Error submitting usage information.')
        except (DownloaderException) as e:
            console_write(e)
            return

        try:
            result = json.loads(result.decode('utf-8'))
            if result['result'] != 'success':
                raise ValueError()
        except (ValueError):
            console_write(
                u'''
                Error submitting usage information for %s
                ''',
                params['package']
            )
