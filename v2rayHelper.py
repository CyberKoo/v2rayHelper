#!/usr/bin/env python3
import argparse
import atexit
import datetime
import fileinput
import hashlib
import inspect
import json
import logging
import os
import platform
import random
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
import uuid
import zipfile
from abc import ABC, abstractmethod
from urllib.error import URLError
from urllib.parse import urlparse


class V2rayHelperException(Exception):
    pass


class UnsupportedPlatformException(V2rayHelperException):
    def __str__(self):
        return 'Unsupported platform: {0}/{1} ({2})'.format(platform.system(), platform.machine(), platform.version())


class MetaFetchException(V2rayHelperException):
    pass


class OSHandler(ABC):
    def __init__(self):
        super().__init__()
        self._post_init()

    def _post_init(self):
        logging.debug('executing base class post_init')

        # clean-up and create temp folder
        OSHelper.remove_if_exists(OSHelper.get_temp())
        OSHelper.mkdir(OSHelper.get_temp(), 0o644)

    @staticmethod
    def _get_github_url(path):
        return 'https://raw.githubusercontent.com/waf7225/v2rayHelper/master/{}'.format(path)

    @staticmethod
    def _get_metadata(version, file_name):
        url = 'https://github.com/v2ray/v2ray-core/releases/download/{}/metadata.txt'.format(version)
        s_counter = 0
        metadata = []

        logging.info('Fetch metadata for version %s', version)
        try:
            with urllib.request.urlopen(url) as response:
                for line in response.read().decode('utf-8').splitlines():
                    data = line.split()
                    data_len = len(data)
                    if data_len == 0:
                        s_counter = 0
                    elif data_len == 2:
                        if s_counter >= 1:
                            metadata.append(data[1])
                            s_counter += 1

                        if data[0] == 'File:' and data[1] == file_name:
                            logging.debug('metadata for %s has been found', file_name)
                            s_counter += 1

                if len(metadata) != 0:
                    return metadata

                raise MetaFetchException('Unable to to find the metadata for {}'.format(file_name))
        except URLError as e:
            raise MetaFetchException('Unable to fetch the Metadata', e)

    @staticmethod
    def _sha1_file(file_name):
        sha1sum = hashlib.sha1()
        with open(file_name, 'rb') as source:
            block = source.read(65536)
            while len(block) != 0:
                sha1sum.update(block)
                block = source.read(65536)

        return sha1sum.hexdigest()

    @staticmethod
    def _extract_file(path, output):
        with zipfile.ZipFile(path, 'r') as zip_ref:
            zip_ref.extractall(output)
            return zip_ref.namelist()[0]

    @staticmethod
    @abstractmethod
    def _target_os():
        pass

    @staticmethod
    @abstractmethod
    def _get_conf_dir():
        pass

    @staticmethod
    @abstractmethod
    def _get_base_path():
        pass

    @abstractmethod
    def _place_file(self, path_from):
        pass

    @abstractmethod
    def install(self, version, filename):
        pass

    @abstractmethod
    def upgrade(self, version, filename):
        pass

    @abstractmethod
    def remove(self):
        pass

    @abstractmethod
    def purge(self, confirmed):
        if not confirmed:
            raise V2rayHelperException('The following arguments are required: --sure')


class UnixLikeHandler(OSHandler, ABC):
    """
    A generic unix like system handler
    """

    def __init__(self, root_required=False):
        super().__init__()
        self._executables = ['v2ray', 'v2ctl']

        if root_required:
            if os.getuid() != 0:
                UnixLikeHandler._relaunch_with_root()

    @staticmethod
    @abstractmethod
    def _service(action):
        pass

    @abstractmethod
    def _install_control_script(self):
        pass

    @abstractmethod
    def _auto_start_set(self, status):
        pass

    @staticmethod
    def _relaunch_with_root():
        # ask for root privileges
        logging.info('Re-lunching with root privileges...')
        if CommandHelper.exists('sudo'):
            logging.debug('Found sudo, I\'m going to use sudo to re-launch this software.')
            os.execvp('sudo', ['sudo', '/usr/bin/env', 'python3'] + sys.argv)
        elif CommandHelper.exists('su'):
            logging.debug('Found su, I\'m going to use su to re-launch this software.')
            os.execvp('su', ['su', '-c', ' '.join(['/usr/bin/env python3'] + sys.argv)])
        else:
            logging.debug('Oops, neither sudo nor su is found on this machine, throw an exception')
            raise V2rayHelperException('Sorry, cannot gain root privilege.')

    def _validate_download(self, filename, metadata):
        if len(metadata) != 0:
            # validate size
            file_size = os.path.getsize(filename)
            sha1 = self._sha1_file(filename)

            if int(metadata[0]) != file_size:
                raise V2rayHelperException('Assertion failed, expected Size {}, got {}.'.format(metadata[0], file_size))

            if metadata[1] != sha1:
                raise V2rayHelperException('Assertion failed, expected SHA1 {}, got {}.'.format(metadata[1], sha1))

            logging.debug('actual size %d, expected size %d', file_size, int(metadata[0]))
            logging.debug('actual sha1 %s, expected sha1 %s', sha1, metadata[1])

            logging.info('File %s has passed the validation.', os.path.basename(filename))
        else:
            raise V2rayHelperException('Failed to perform validation, invalid metadata')

    def _place_file(self, path_from):
        path_to = '/opt/v2ray/'

        # remove old file
        OSHelper.remove_if_exists(path_to)

        # move downloaded file to path_to
        shutil.move(path_from, path_to)
        logging.debug('move %s to %s', path_from, path_to)

        # change file and dir permission
        logging.debug('Change permission for dir %s', path_to)
        for root, dirs, files in os.walk(path_to):
            for _dir in dirs:
                logging.debug('set dir permission %s to %d', os.path.join(root, _dir), 755)
                os.chmod(os.path.join(root, _dir), 0o755)
            for file in files:
                if file not in self._executables:
                    logging.debug('set file permission %s to %d', os.path.join(root, file), 644)
                    os.chmod(os.path.join(root, file), 0o644)
                else:
                    logging.debug('set file permission %s to %d', os.path.join(root, file), 755)
                    os.chmod(os.path.join(root, file), 0o777)

    def install(self, version, filename):
        # download zip file
        full_path = OSHelper.get_temp(file=filename)
        Downloader('https://github.com/v2ray/v2ray-core/releases/download/{}/{}'.format(version, filename),
                   filename).start()

        # validate downloaded file with metadata
        try:
            self._validate_download(full_path, self._get_metadata(version, filename))
        except MetaFetchException as ex:
            logging.error('%s, validation process is skipped', ex)

        # extract zip file
        extracted_dir = self._extract_file(full_path, OSHelper.get_temp())
        logging.debug('file extracted to %s', extracted_dir)

        # remove zip file
        OSHelper.remove_if_exists(full_path)

        # place v2ray to /opt/v2ray
        self._place_file(OSHelper.get_temp(path=[extracted_dir]))

        # create soft link, for *nix
        for file in self._executables:
            symlink_path = '{}/{}'.format(self._get_base_path(), file)

            # delete the old symlink
            OSHelper.remove_if_exists(symlink_path)

            # create symbol link
            os.symlink('/opt/v2ray/{}'.format(file), symlink_path)

        # add user
        UnixLikeHelper.add_user(self._get_user_prefix(), self._add_user_command(), 'v2ray')

        # script
        self._install_control_script()
        self._auto_start_set('enable')

        # download and place the default config file
        conf_dir = self._get_conf_dir()

        # create default configuration file path
        OSHelper.mkdir(conf_dir, 0o755)
        config_file = '{}/config.json'.format(conf_dir)
        new_token = None

        if not os.path.exists(config_file):
            # download config file
            Downloader(self._get_github_url('misc/config.json'), 'config.json').start()
            shutil.move(OSHelper.get_temp(file='config.json'), config_file)

            # replace default value with randomly generated one
            new_token = [str(uuid.uuid4()), str(random.randint(50000, 65535))]
            FileHelper.replace('{}/config.json'.format(conf_dir), [
                ['dbe16381-f905-4b88-946f-dfc21ed9be29', new_token[0]],
                # ['0.0.0.0', str(get_ip())],
                ['12345', new_token[1]]
            ])
        else:
            logging.info('%s is already exists, skip installing config.json', config_file)

        # start v2ray
        self._service('start')

        # print message
        logging.info('Successfully installed v2ray-{}'.format(version))

        if new_token is not None:
            logging.info('v2ray is now bind on %s:%s', OSHelper.get_ip(), new_token[1])
            logging.info('uuid: %s', new_token[0])
            logging.info('alterId: %d', 64)

    def upgrade(self, version, filename):
        # download zip file
        full_path = OSHelper.get_temp(file=filename)
        Downloader('https://github.com/v2ray/v2ray-core/releases/download/{}/{}'.format(version, filename),
                   filename).start()

        # validate downloaded file with metadata
        try:
            self._validate_download(full_path, self._get_metadata(version, filename))
        except MetaFetchException as ex:
            logging.error('%s, validation process is skipped', ex)

        # extract zip file
        extracted_dir = self._extract_file(full_path, OSHelper.get_temp())
        logging.debug('file extracted to %s', extracted_dir)

        # remove zip file
        OSHelper.remove_if_exists(full_path)

        # place v2ray to /opt/v2ray
        self._place_file(OSHelper.get_temp(path=[extracted_dir]))

        # restart v2ray
        self._service('restart')
        logging.info('Successfully upgraded to v2ray-%s', version)

    def remove(self):
        logging.info('Uninstalling...')
        # stop v2ray process
        try:
            logging.info('Stop v2ray process')
            self._service('stop')

            logging.info('Disable auto start')
            self._auto_start_set(False)
        except subprocess.CalledProcessError:
            logging.warning('v2ray service file is not found!!!')

        # remove symbol links
        logging.info('Deleting symbol links')
        for name in ['v2ray', 'v2ctl']:
            path = shutil.which(name)
            if path is not None:
                OSHelper.remove_if_exists(path)

        # remove the real installed folder
        logging.info('Deleting v2ray directory')
        OSHelper.remove_if_exists('/opt/v2ray/')
        OSHelper.remove_if_exists('/usr/local/v2ray/')

    def purge(self, confirmed):
        """
        this is a default implementation for purge function
        :param confirmed: Bool
        :return: None
        """
        super().purge(confirmed)

        # uninstall first
        self.remove()

        # delete configuration
        logging.info('Deleting configuration file')
        OSHelper.remove_if_exists(self._get_conf_dir())

        # delete user/group
        logging.info('Deleting User/Group v2ray')
        UnixLikeHelper.delete_user(self._get_user_prefix())

        # delete all other file/folders
        logging.info('Deleting all other files')
        OSHelper.remove_if_exists('/etc/systemd/system/v2ray.service')

    @staticmethod
    def _get_user_prefix():
        return ''

    @staticmethod
    def _add_user_command():
        return None


class LinuxHandler(UnixLikeHandler):
    def __init__(self):
        super().__init__(True)

    def _post_init(self):
        super()._post_init()

        if self._is_legacy_os():
            logging.warning('You\'re running an outdated linux version, some operation will not be supported.')

    @staticmethod
    def _target_os():
        return ['linux']

    @staticmethod
    def _get_conf_dir():
        return '/etc/v2ray'

    @staticmethod
    def _get_base_path():
        return '/usr/bin'

    @staticmethod
    def _is_legacy_os():
        return not os.path.isdir('/run/systemd/system/')

    def _auto_start_set(self, status):
        """
        :param status: Bool
        :return:
        """
        self._service('enable' if status else 'disable')

    @staticmethod
    def _service(action):
        if not LinuxHandler._is_legacy_os():
            CommandHelper.execute('systemctl {} v2ray'.format(action))

    def _install_control_script(self):
        if not self._is_legacy_os():
            # download systemd control script
            Downloader(self._get_github_url('misc/v2ray.service'), 'v2ray.service').start()
            # move this service file to /etc/systemd/system/
            shutil.move(OSHelper.get_temp(file='v2ray.service'), '/etc/systemd/system/v2ray.service')


class MacOSHandler(UnixLikeHandler):
    def _post_init(self):
        super()._post_init()
        # check if brew is installed
        if not CommandHelper.exists('brew'):
            raise V2rayHelperException('This script requires Homebrew, please install Homebrew first')

    @staticmethod
    def _get_conf_dir():
        pass

    @staticmethod
    def _get_base_path():
        pass

    @staticmethod
    def _target_os():
        return ['darwin']

    @staticmethod
    def _service(action):
        CommandHelper.execute('brew services {} v2ray-core'.format(action))

    def _auto_start_set(self, status):
        self._service('enable' if status else 'disable')

    def _install_control_script(self):
        pass

    def install(self, version, filename):
        # Install the official tap
        logging.info('Install the official tap...')
        CommandHelper.execute('brew tap v2ray/v2ray')

        # install v2ray
        logging.info('Install v2ray...')
        CommandHelper.execute('brew install v2ray-core')

        # set auto-start
        logging.info('register v2ray to launch at login...')
        CommandHelper.execute('brew services start v2ray-core')

        # print message
        logging.info('Successfully installed v2ray')

    def upgrade(self, version, filename):
        # upgrading v2ray
        logging.info('Upgrade v2ray...')
        try:
            CommandHelper.execute('brew upgrade v2ray-core')

            logging.info('V2ray Upgraded')

            logging.info('Restart v2ray...')

            self._service('restart')
        except subprocess.CalledProcessError:
            raise V2rayHelperException('Cannot upgrade v2ray, subprocess returned an error')

    def remove(self):
        # remove v2ray
        logging.info('Uninstalling v2ray...')
        try:
            CommandHelper.execute('brew remove v2ray-core')
        except subprocess.CalledProcessError:
            logging.error('Cannot remove v2ray, subprocess returned an error')

    def purge(self, confirmed):
        super().purge(confirmed)
        self.remove()
        logging.info('Untapping v2ray/v2ray')
        CommandHelper.execute('brew untap v2ray/v2ray')
        logging.info('Remove ')


class BSDHandler(UnixLikeHandler, ABC):
    def __init__(self):
        super().__init__(True)

    def _auto_start_set(self, status):
        rc_file_path = '/etc/rc.conf'

        if status:
            # Enable
            if not FileHelper.contains(rc_file_path, 'v2ray_enable'):
                with open(rc_file_path, 'a+') as file:
                    file.write('\nv2ray_enable="YES"\n')
        else:
            # Disable
            if FileHelper.contains(rc_file_path, 'v2ray_enable'):
                with open(rc_file_path, 'r+') as file:
                    new_f = file.readlines()
                    file.seek(0)
                    for line in new_f:
                        if 'v2ray_enable' not in line:
                            file.write(line)
                    file.truncate()

    @staticmethod
    def _get_base_path():
        return '/usr/local/bin'


class FreeBSDHandler(BSDHandler):
    @staticmethod
    def _target_os():
        return ['freebsd']

    @staticmethod
    def _get_conf_dir():
        return '/usr/local/etc/v2ray'

    @staticmethod
    def _get_user_prefix():
        return 'pw '

    @staticmethod
    def _service(action):
        CommandHelper.execute('service v2ray {}'.format(action))

    def _install_control_script(self):
        Downloader(self._get_github_url('misc/v2ray.freebsd'), 'v2ray').start()
        path = '/usr/local/etc/rc.d/v2ray'

        shutil.move(OSHelper.get_temp(file='v2ray'), path)
        os.chmod(path, 0o555)

        # create folder for pid file
        UnixLikeHelper.mkdir_chown('/var/run/v2ray/', 0o755, 'v2ray', 'v2ray')

    def purge(self, confirmed):
        super().purge(confirmed)

        OSHelper.remove_if_exists('/usr/local/etc/rc.d/v2ray')
        OSHelper.remove_if_exists('/var/run/v2ray/')


class OpenBSDHandler(BSDHandler):
    @staticmethod
    def _target_os():
        return ['openbsd']

    @staticmethod
    def _get_conf_dir():
        return '/etc/v2ray'

    @staticmethod
    def _service(action):
        CommandHelper.execute('rcctl {} v2ray'.format(action))

    @staticmethod
    def _add_user_command():
        return '{0}useradd -md /var/lib/{1} -s /sbin/nologin -g {1} {1}'

    def _install_control_script(self):
        Downloader(self._get_github_url('misc/v2ray.openbsd'), 'v2ray').start()
        path = '/etc/rc.d/v2ray'

        shutil.move(OSHelper.get_temp(file='v2ray'), path)
        os.chmod(path, 0o555)

        # create folder for pid file
        UnixLikeHelper.mkdir_chown('/var/run/v2ray/', 0o755, 'v2ray', 'v2ray')

    def purge(self, confirmed):
        super().purge(confirmed)

        # delete rc.d file
        OSHelper.remove_if_exists('/etc/rc.d/v2ray')


class WindowsHandler(OSHandler):
    def _post_init(self):
        super(WindowsHandler, self)._post_init()
        logging.debug('execute windows handler post_init')

        raise UnsupportedPlatformException()

        import ctypes, sys
        if not ctypes.windll.shell32.IsUserAnAdmin():
            # Re-run the program with admin rights
            ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, __file__, None, 1)
        else:
            super()._post_init()

    @staticmethod
    def _target_os():
        return ['windows']

    @staticmethod
    def _get_conf_dir():
        pass

    @staticmethod
    def _get_base_path():
        pass

    def _place_file(self, path_from):
        pass

    def install(self, version, filename):
        pass

    def upgrade(self, version, filename):
        pass

    def remove(self):
        pass

    def purge(self, confirmed):
        pass


class Downloader:
    def __init__(self, url, file_name):
        # init system variable
        self._url = url
        self._file_name = file_name

        # variable for report hook
        self._last_reported = 0
        self._last_displayed = 0
        self._start_time = 0

    @staticmethod
    def _format_size(size, is_speed=False):
        n = 0
        unit = {0: '', 1: 'K', 2: 'M', 3: 'G', 4: 'T'}

        while size > 1024:
            size /= 1024
            n += 1

        return '{:6.2f} {}B{} '.format(size, unit[n], '/s' if is_speed else '')

    @staticmethod
    def _format_time(_time, _append=''):
        return '{:.8}{}'.format(str(datetime.timedelta(seconds=_time)), _append)

    @staticmethod
    def _get_remain_tty_width(occupied):
        width = 0
        if CommandHelper.exists('stty'):
            width = int(CommandHelper.execute('stty size').split()[1])

        return width - occupied if width > occupied else 0

    def _display_base_name(self, base_name):
        name_len = len(base_name)

        if name_len > 25:
            if name_len - self._last_displayed > 25:
                self._last_displayed += 1
                return base_name[self._last_displayed - 1: self._last_displayed + 24]
            else:
                self._last_displayed = 0
                return base_name
        else:
            return base_name

    def start(self):
        base_name = os.path.basename(urlparse(self._url).path)
        file_name = self._file_name if self._file_name is not None else base_name

        # full path
        path = OSHelper.get_temp(file=file_name)
        temp_path = '{}.{}'.format(path, 'v2tmp')

        # delete temp file
        OSHelper.remove_if_exists(temp_path)

        # record down start time
        self._start_time = time.time()

        def _report_hook(block_num, block_size, total_size):
            read_so_far = block_num * block_size
            if total_size > 0:
                duration = int(time.time() - self._start_time)
                speed = int(read_so_far) / duration if duration != 0 else 1
                percent = read_so_far * 1e2 / total_size
                estimate = int((total_size - read_so_far) / speed) if speed != 0 else 0
                percent = 100.00 if percent > 100.00 else percent

                # clear line if available
                width = self._get_remain_tty_width(96)
                basic_format = '\rFetching: {:<25.25s} {:<15s} {:<15.15s} {:<15.15s} {}{:>{width}}'

                if read_so_far < total_size:
                    # report rate 0.1s
                    if abs(time.time() - self._last_reported) > 0.1:
                        self._last_reported = time.time()
                        sys.stdout.write(
                            basic_format.format(
                                self._display_base_name(base_name), '{:8.2f}%'.format(percent),
                                self._format_size(total_size), self._format_size(speed, True),
                                self._format_time(estimate, ' ETA'), '', width=width)
                        )
                else:
                    # near the end
                    sys.stdout.write(
                        basic_format.format(
                            base_name, '{:8.2f}%'.format(percent), self._format_size(total_size),
                            self._format_size(speed, True),
                            self._format_time(duration), '', width=width)
                    )

                    sys.stdout.write('\n')
            # total size is unknown
            else:
                # TODO format output
                sys.stdout.write("\r read {}".format(read_so_far))
                sys.stdout.flush()

        try:
            urllib.request.urlretrieve(self._url, temp_path, _report_hook)
        except URLError:
            raise V2rayHelperException('Unable to fetch url: {}'.format(self._url))

        os.rename(temp_path, path)


class OSHelper:
    @staticmethod
    def get_name():
        return platform.system().lower()

    @staticmethod
    def get_temp(base_dir='v2rayHelper', path=None, file=''):
        full_path = ''
        if path is not None:
            full_path = '/'.join(path)

        return '{}/{}/{}/{}'.format(tempfile.gettempdir().replace('\\', '/'), base_dir, full_path, file) \
            .replace('//', '/')

    @staticmethod
    def get_ip():
        """
        from https://stackoverflow.com/questions/166506/finding-local-ip-addresses-using-pythons-stdlib
        modified by Kotarou
        :return: ip address
        """
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            try:
                # doesn't even have to be reachable
                s.connect(('10.255.255.255', 1))
                ip_address = s.getsockname()[0]
            except:
                ip_address = '127.0.0.1'

        return ip_address

    @staticmethod
    def remove_if_exists(path):
        logging.debug('trying to delete %s', path)

        if os.path.exists(path) or os.path.islink(path):
            if os.path.isdir(path):
                logging.debug('%s is a director, deleted', path)
                shutil.rmtree(path)
            else:
                logging.debug('%s is a regular file or symbol link, deleted', path)
                os.unlink(path)
        else:
            logging.debug('%s does\'t exists, ignore', path)

    @staticmethod
    def mkdir(path, permission=0o755):
        if not os.path.exists(path) and not os.path.islink(path):
            os.mkdir(path, permission)
            logging.debug('directory %s created with permission %o', path, permission)
        else:
            logging.debug('mkdir: cannot create directory "%s": File exists', path)


class UnixLikeHelper(OSHelper):
    @staticmethod
    def chown(path, user=None, group=None):
        if user is None and group is None:
            raise V2rayHelperException('username and group cannot be empty at the same time.')

        if user is not None:
            shutil.chown(path, user=user)
            logging.debug('the owner of directory %s change to %s', path, user)
        if group is not None:
            shutil.chown(path, group=group)
            logging.debug('the owner of directory %s change to %s:%s', path, user, group)

    @staticmethod
    def mkdir_chown(path, perm=0o755, user=None, group=None):
        OSHelper.mkdir(path, perm)
        UnixLikeHelper.chown(path, user, group)

    @staticmethod
    def add_user(prefix, command=None, user_name='v2ray'):
        import grp, pwd

        def _try_group():
            grp.getgrnam(user_name)

        def _try_user():
            pwd.getpwnam(user_name)

        def _try_add_group():
            CommandHelper.execute('{}groupadd {}'.format(prefix, user_name))

        def _try_add_user():
            # delete the home folder
            OSHelper.remove_if_exists('/var/lib/{}'.format(user_name))

            create_user = '{0}useradd {1} -md /var/lib/{1} -s /sbin/nologin -g {1}'.format(prefix, user_name) \
                if command is None else command.format(prefix, user_name)

            CommandHelper.execute(create_user)

        # add group
        Utils.closure_try(_try_group, KeyError, _try_add_group)

        # add user
        Utils.closure_try(_try_user, KeyError, _try_add_user)

    @staticmethod
    def delete_user(prefix, user_name='v2ray', group_name='v2ray', delete_group=True):
        import grp, pwd

        def _try_delete_user():
            pwd.getpwnam(user_name)
            CommandHelper.execute('{0}userdel {1}'.format(prefix, user_name))

            # delete if exists
            OSHelper.remove_if_exists('/var/lib/{}'.format(user_name))

        def _try_delete_group():
            grp.getgrnam(group_name)
            CommandHelper.execute('{}groupdel {}'.format(prefix, group_name))

        def _do_nothing():
            pass

        # delete user
        Utils.closure_try(_try_delete_user, KeyError, _do_nothing)

        # delete group
        if delete_group:
            Utils.closure_try(_try_delete_group, KeyError, _do_nothing)


class FileHelper:
    @staticmethod
    def contains(file_name, data):
        with open(file_name) as file:
            for line in file:
                if line.find(data) is not -1:
                    return True

        return False

    @staticmethod
    def replace(_filename, _replace_pair):
        with fileinput.FileInput(_filename, inplace=True) as file:
            for line in file:
                for replace in _replace_pair:
                    line = line.replace(replace[0], replace[1])
                print(line, end='')


class CommandHelper:
    @staticmethod
    def execute(command, encoding='utf-8'):
        """
        :param command: shell command
        :param encoding: encoding, default utf-8
        :return: execution result
        """
        return subprocess.check_output(command, shell=True, stderr=subprocess.DEVNULL).decode(encoding)

    @staticmethod
    def exists(command):
        def _try():
            CommandHelper.execute('type {}'.format(command))
            return True

        def _except():
            return False

        return Utils.closure_try(_try, subprocess.CalledProcessError, _except)

    @staticmethod
    def which_exists(_commands):
        if Utils.is_collection(_commands):
            for command in _commands:
                if CommandHelper.exists(command):
                    return command
            return None
        else:
            raise TypeError()


class V2RayAPI:
    def __init__(self):
        self._json = None
        self._pre_release = None
        self._latest_version = None

    def fetch(self):
        api_url = 'https://api.github.com/repos/v2ray/v2ray-core/releases/latest'

        try:
            with urllib.request.urlopen(api_url) as response:
                self._json = json.loads(response.read().decode('utf8'))
                self._pre_release = '(pre release)' if self._json['prerelease'] else ''
                self._latest_version = self._json['tag_name']
        except URLError:
            raise V2rayHelperException('Unable to fetch data from API')

    @staticmethod
    def _get_arch(machine):
        supported = {
            '32': ['i386'],
            '64': ['x86_64', 'amd64'],
            'arm': ['armv7l', 'armv7', 'armv7hf', 'armv7hl'],
            'arm64': ['aarch64']
        }

        # make it to lower case to maintain the compatibility across all platforms
        for key in supported:
            if machine.lower() in supported[key]:
                return key

        raise UnsupportedPlatformException()

    def search(self, _machine):
        # skip macos
        if OSHelper.get_name() == 'darwin':
            return ''

        search_name = '{}-{}.zip'.format(OSHelper.get_name(), self._get_arch(_machine))
        for assets in self._json['assets']:
            if assets['name'].find(search_name) != -1:
                return assets['name']

        raise UnsupportedPlatformException()

    def get_latest_version(self):
        return self._latest_version

    def get_pre_release(self):
        return self._pre_release


class V2rayHelper:
    def __init__(self):
        self._arch = platform.architecture()[0]
        self._arch_num = self._arch[0:2]
        self._machine = platform.machine()
        self._api = V2RayAPI()

    @staticmethod
    def _get_all_subclasses(cls):
        all_subclasses = []

        for subclass in cls.__subclasses__():
            # exclude abstract class
            if not inspect.isabstract(subclass):
                all_subclasses.append(subclass)
            all_subclasses.extend(V2rayHelper._get_all_subclasses(subclass))

        return all_subclasses

    @staticmethod
    @atexit.register
    def _cleanup():
        logging.debug('Clean-up')

        # delete temp folder
        OSHelper.remove_if_exists(OSHelper.get_temp())

    @staticmethod
    def _get_v2ray_version():
        def _try():
            return CommandHelper.execute('v2ray --version').split()[1]

        def _except():
            return None

        return Utils.closure_try(_try, subprocess.CalledProcessError, _except)

    def _get_os_handler(self):
        # find the correlated OSHandler
        for cls in self._get_all_subclasses(OSHandler):
            logging.debug('OSHandler: %s, target os: %s', cls.__name__, cls._target_os())
            if OSHelper.get_name() in cls._target_os():
                logging.debug('Found OSHandler: %s, returning', cls.__name__)

                return cls

        raise UnsupportedPlatformException()

    def run(self, args):
        # make sure init function is executed
        handler = (self._get_os_handler())()
        version = self._get_v2ray_version()

        # get information from API
        self._api.fetch()
        file_name = self._api.search(self._machine)
        latest_version = self._api.get_latest_version()

        # display information obtained from api
        logging.info('Hi there, the latest version of v2ray is %s %s',
                     latest_version, self._api.get_pre_release()
                     )

        # display operating system information
        logging.info('Operating system: %s-%s (%s)',
                     OSHelper.get_name(), self._arch_num, self._machine
                     )

        logging.info('Currently installed version: %s...', version)

        # execute
        if args.install:
            if args.force is False:
                if version is not None:
                    raise V2rayHelperException('v2ray is already installed, use --force to reinstall.')

            handler.install(latest_version, file_name)
        elif args.upgrade:
            if version is None:
                raise V2rayHelperException('v2ray must be installed before you can upgrade it.')

            if version != latest_version or args.force:
                if args.force:
                    logging.info('You already installed the latest version, forced to upgrade')

                    handler.upgrade(latest_version, file_name)
            else:
                raise V2rayHelperException('You already installed the latest version, use --force to upgrade.')
        elif args.remove:
            if args.force is False:
                if version is None:
                    raise V2rayHelperException('v2ray is not installed, you cannot uninstall it.')
            handler.remove()
        elif args.purge:
            handler.purge(args.sure)
        elif args.auto:
            if version is None:
                handler.install(latest_version, file_name)
            else:
                if version != latest_version:
                    handler.upgrade(latest_version, file_name)
                else:
                    raise V2rayHelperException('You already installed the latest version, use --force to upgrade.')


class Utils:
    @staticmethod
    def signal_handler(signal_number):
        """
        from http://code.activestate.com/recipes/410666-signal-handler-decorator/

        A decorator to set the specified function as handler for a signal.
        This function is the 'outer' decorator, called with only the (non-function)
        arguments
        """

        # create the 'real' decorator which takes only a function as an argument
        def __decorator(_function):
            signal.signal(signal_number, _function)
            return _function

        return __decorator

    @staticmethod
    def is_collection(arg):
        return True if hasattr(arg, '__iter__') and not isinstance(arg, (str, bytes)) else False

    @staticmethod
    def closure_try(__try, __except, __on_except):
        try:
            return __try()
        except __except:
            return __on_except()

    @staticmethod
    def get_args():
        parser = argparse.ArgumentParser()
        group = parser.add_mutually_exclusive_group()
        group.add_argument('-A', '--auto', action='store_true', default=True, help='automatic mode')
        group.add_argument('-I', '--install', action='store_true', help='install v2ray')
        group.add_argument('-U', '--upgrade', action='store_true', help='upgrade v2ray')
        group.add_argument('-R', '--remove', action='store_true', help='remove v2ray')
        group.add_argument('-P', '--purge', action='store_true', help='remove v2ray and configure file')
        parser.add_argument('--sure', action='store_true', help='confirm action')
        parser.add_argument('--force', action='store_true', help='force to do the selected action')
        parser.add_argument('--debug', action='store_true', help='show all logs')

        return parser.parse_args()


@Utils.signal_handler(signal.SIGINT)
def _sigint_handler(signum, frame):
    logging.warning('Quitting...')
    exit(signum)


if __name__ == "__main__":
    args = Utils.get_args()

    # set logger
    logging.basicConfig(
        format='%(asctime)s [%(threadName)s] [%(levelname)8s]  %(message)s',
        level=logging.DEBUG if args.debug else logging.INFO,
        handlers=[
            logging.StreamHandler()
        ]
    )

    logging.debug('debug model enabled')

    try:
        helper = V2rayHelper()
        helper.run(args)
    # V2rayHelperException handling
    except V2rayHelperException as e:
        logging.critical(e)
        exit(-1)
