#!/usr/bin/env python3
import datetime
import fileinput
import hashlib
import os
import platform
import random
import shutil
import signal
import socket
import subprocess
import json
import sys
import time
import urllib.request
import uuid
import zipfile
from pathlib import Path
from urllib.parse import urlparse


class UnsupportedPlatform(Exception):
    pass


class ValidationError(Exception):
    pass


def get_ip():
    # from https://stackoverflow.com/questions/166506/finding-local-ip-addresses-using-pythons-stdlib?utm_medium=organic&utm_source=google_rich_qa&utm_campaign=google_rich_qa
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # doesn't even have to be reachable
        s.connect(('10.255.255.255', 1))
        IP = s.getsockname()[0]
    except:
        IP = '127.0.0.1'
    finally:
        s.close()
    return IP


def execute_external_command(_command):
    return subprocess.check_output(_command, shell=True, stderr=subprocess.DEVNULL).decode('utf-8')


def remove_if_exists(_path):
    if os.path.exists(_path):
        if os.path.isdir(_path):
            shutil.rmtree(_path)
        else:
            os.unlink(_path)


def chown(_path, _user=None, _group=None):
    if _user is None and _group is None:
        raise RuntimeError

    if _user is not None:
        shutil.chown(_path, user=_user)
    if _group is not None:
        shutil.chown(_path, group=_group)


def mkdir(_path, _perm=0o755):
    if not os.path.exists(_path) and not os.path.islink(_path):
        os.mkdir(_path, _perm)


def mkdir_chown(_path, _perm=0o755, _user=None, _group=None):
    mkdir(_path, _perm)
    chown(_path, _user, _group)


def replace_content_in_file(_filename, _replace_pair):
    with fileinput.FileInput(_filename, inplace=True) as file:
        for line in file:
            for replace in _replace_pair:
                line = line.replace(replace[0], replace[1])
            print(line, end='')


def closure_try(__try, __except, __on_except):
    try:
        return __try()
    except __except:
        return __on_except()


def is_command_exists(_command):
    def _try():
        execute_external_command('type {}'.format(_command))
        return True

    def _except():
        return False

    return closure_try(_try, subprocess.CalledProcessError, _except)


def which_command_exists(_commands):
    if is_collection(_commands):
        for command in _commands:
            if is_command_exists(command):
                return command
        return None
    else:
        raise TypeError


def is_collection(_arg):
    return True if hasattr(_arg, '__iter__') and not isinstance(_arg, (str, bytes)) else False


def os_is(os_name):
    if is_collection(os_name):
        return True if platform.system().lower() in [x.lower() for x in os_name] else False
    else:
        return platform.system().lower() == os_name.lower()


def os_is_bsd():
    return os_is(['openbsd', 'freebsd', 'netbsd'])


def os_is_nix():
    return os_is_bsd() or os_is('linux')


def os_is_mac():
    return os_is('Darwin')


def os_is_supported():
    return os_is_nix() or os_is_mac()


def get_v2ray_version():
    def _try():
        return execute_external_command('v2ray --version').split()[1]

    def _except():
        return None

    return closure_try(_try, subprocess.CalledProcessError, _except)


def is_systemd():
    return os.path.isdir('/run/systemd/system')


def v2ray_service(command):
    if is_systemd():
        execute_external_command('systemctl {} v2ray'.format(command))
    else:
        execute_external_command('service v2ray {}'.format(command))


def get_os_info():
    system = platform.system()
    arch = platform.architecture()[0][0:2]
    machine = platform.machine()

    supported = {
        'arch': ['X86_64', 'I386'],
        'arm': {
            'arm': ['armv7l', 'armv7', 'armv7hf', 'armv7hl'],
            'arm64': ['armv8']
        }
    }

    if os_is_supported():
        if machine not in supported['arch']:
            for key in supported['arm']:
                if machine in supported['arm'][key]:
                    arch = key
                    break

        return [system.lower(), arch, platform.architecture()[0], machine]

    raise UnsupportedPlatform


def get_latest_version_from_api(os, arch, arch_num, machine):
    api_url = 'https://api.github.com/repos/v2ray/v2ray-core/releases/latest'

    with urllib.request.urlopen(api_url) as response:
        json_response = json.loads(response.read().decode('utf8'))
        pre_release = '(pre release)' if json_response['prerelease'] is True else ''
        latest_version = json_response['tag_name']

        print('Hi there, the latest version of v2ray is {} {}'.format(latest_version, pre_release))
        print('Operating system: {}-{} ({})'.format(os, arch_num, machine))

        for assets in json_response['assets']:
            if assets['name'].find('{}-{}.zip'.format(os, arch)) != -1:
                return [assets['name'], latest_version]


def get_meta_data(version, _file_name):
    url = 'https://github.com/v2ray/v2ray-core/releases/download/{}/metadata.txt'.format(version)
    download_file(url, 'metadata.txt')

    result = []
    with open('/tmp/v2rayHelper/metadata.txt', 'r+') as file:
        for line in file:
            split = line.split()
            if len(split) == 2 and split[0] == 'File:':
                if split[1] == _file_name:
                    # return size and sha1
                    result = [int(file.readline().split()[1]), file.readline().split()[1]]
                    break

    remove_if_exists('/tmp/v2rayHelper/metadata.txt')

    return result


def download_file(_url, _file_name=None, dir='/tmp/v2rayHelper'):
    base_name = os.path.basename(urlparse(_url).path)
    file_name = _file_name if _file_name is not None else base_name

    # full path
    full_path = '{}/{}'.format(dir, file_name)
    temp_full_path = '{}.{}'.format(full_path, 'v2tmp')

    # delete temp file
    remove_if_exists(temp_full_path)

    # variable for report hook
    last_reported = 0
    last_displayed = 0

    # record down start time
    start_time = time.time()

    def __report_hook(block_num, block_size, total_size):
        nonlocal last_displayed
        nonlocal last_reported

        def __format_size(size):
            n = 0
            unit = {0: '', 1: 'K', 2: 'M', 3: 'G', 4: 'T'}

            while size > 1024:
                size /= 1024
                n += 1

            return '{:6.2f} {}B/s '.format(size, unit[n])

        def __format_time(_time, _append=''):
            return '{:.8}{}'.format(str(datetime.timedelta(seconds=_time)), _append)

        def __get_remain_tty_width(occupied):
            _width = 0
            if is_command_exists('stty'):
                _width = int(execute_external_command('stty size').split()[1])

            return _width - occupied if _width > occupied else 0

        def __display_base_name(base_name):
            name_len = len(base_name)
            nonlocal last_displayed

            if name_len > 25:
                if name_len - last_displayed > 25:
                    last_displayed += 1
                    return base_name[last_displayed - 1: last_displayed + 24]
                else:
                    last_displayed = 0
                    return base_name
            else:
                return base_name

        read_so_far = block_num * block_size
        if total_size > 0:
            duration = int(time.time() - start_time)
            speed = int(read_so_far) / duration if duration != 0 else 1
            percent = read_so_far * 1e2 / total_size
            estimate = int((total_size - read_so_far) / speed) if speed != 0 else 0
            percent = 100.00 if percent > 100.00 else percent

            # clear line if available
            width = __get_remain_tty_width(96)
            basic_format = '\rFetching: {:<25.25s} {:<15s} {:<15.15s} {:<15.15s} {}{:>{width}}'

            if read_so_far < total_size:
                # report rate 0.1s
                if abs(time.time() - last_reported) > 0.1:
                    last_reported = time.time()
                    sys.stdout.write(
                        basic_format.format(
                            __display_base_name(base_name), '{:8.2f}%'.format(percent),
                            __format_size(total_size), __format_size(speed),
                            __format_time(estimate, ' ETA'), '', width=width)
                    )
                else:
                    pass
            else:
                # near the end
                sys.stdout.write(
                    basic_format.format(
                        base_name, '{:8.2f}%'.format(percent), __format_size(total_size), __format_size(speed),
                        __format_time(duration), '', width=width)
                )

                sys.stdout.write('\n')
        # total size is unknown
        else:
            # TODO format output
            sys.stdout.write("\r read {}".format(read_so_far))

            sys.stdout.flush()

    urllib.request.urlretrieve(_url, temp_full_path, __report_hook)
    os.rename(temp_full_path, full_path)


def extract_file(path, output):
    with zipfile.ZipFile(path, 'r') as zip_ref:
        zip_ref.extractall(output)


def place_file(path_from):
    install_path = ['/opt/v2ray/', '/usr/local/v2ray/']
    executables = ['v2ray', 'v2ctl']

    path_to = install_path[0]
    for path in install_path:
        if os.path.exists(path):
            path_to = path

    # remove old file
    remove_if_exists(path_to)

    # move downloaded file to path_to
    shutil.move(path_from, path_to)

    # change file and dir permission
    for root, dirs, files in os.walk(path_to):
        for dir in dirs:
            os.chmod(os.path.join(root, dir), 0o755)
        for file in files:
            if file not in executables:
                os.chmod(os.path.join(root, file), 0o644)
            else:
                os.chmod(os.path.join(root, file), 0o777)

    return path_to


def get_extracted_path(filename, version):
    split_folder = filename[0:-4].split('-')
    split_folder.insert(1, version)

    return '-'.join(split_folder)


def install_start_script():
    if os_is('linux'):
        # create systemd file or rc.d
        if is_systemd():
            download_file('https://raw.githubusercontent.com/waf7225/v2rayHelper/master/misc/v2ray.service',
                          'v2ray.service')

            shutil.move('/tmp/v2rayHelper/v2ray.service', '/etc/systemd/system/v2ray.service')
        else:
            # todo add support for legacy init scripts
            pass
    elif os_is_bsd():
        download_file('https://raw.githubusercontent.com/waf7225/v2rayHelper/master/misc/v2ray.freebsd', 'v2ray')

        shutil.move('/tmp/v2rayHelper/v2ray', '/usr/local/etc/rc.d/v2ray')
        os.chmod('/usr/local/etc/rc.d/v2ray', 0o555)

        # create folder for pid file
        mkdir_chown('/var/run/v2ray/', 0o755, 'v2ray', 'v2ray')


def enable_auto_start():
    if os_is_bsd():
        with open('/etc/rc.conf', 'a+') as file:
            file.write('\nv2ray_enable="YES"')
    elif os_is('linux'):
        if is_systemd():
            v2ray_service('enable')


def install_default_config_file():
    conf_dir = None

    if os_is('linux'):
        conf_dir = '/etc/v2ray'
    elif os_is_bsd():
        conf_dir = '/usr/local/etc/v2ray'

    if conf_dir is not None:
        # create default configuration file path
        mkdir(conf_dir, 0o755)
        config_file = '{}/config.json'.format(conf_dir)

        if not os.path.exists(config_file):
            # download config file
            download_file('https://raw.githubusercontent.com/waf7225/v2rayHelper/master/misc/config.json',
                          'config.json')
            shutil.move('/tmp/v2rayHelper/config.json', config_file)

            # replace default value with randomly generated one
            replace = [str(uuid.uuid4()), str(random.randint(50000, 65535))]
            replace_content_in_file('{}/config.json'.format(conf_dir), [
                ['dbe16381-f905-4b88-946f-dfc21ed9be29', replace[0]],
                # ['0.0.0.0', str(get_ip())],
                ['12345', replace[1]]
            ])

            return replace
        else:
            print('{} is already exists, skip installing config.json'.format(config_file))

    return None


def add_user(_user_ame=None):
    name = _user_ame if _user_ame is not None else 'v2ray'
    prefix = 'pw ' if os_is('freebsd') else ''

    def _try_group():
        import grp
        grp.getgrnam(name)

    def _try_user():
        import pwd
        pwd.getpwnam(name)

    def _try_add_group():
        execute_external_command('{}groupadd {}'.format(prefix, name))

    def _try_add_user():
        # delete if exists
        if os.path.exists('/var/lib/{}'.format(name)):
            shutil.rmtree('/var/lib/{}'.format(name))

        create_user = '{0}useradd -md /var/lib/{1} -s /sbin/nologin -g {1} {1}'.format(prefix, name)
        execute_external_command(create_user)

    # add group
    closure_try(_try_group, KeyError, _try_add_group)

    # add user
    closure_try(_try_user, KeyError, _try_add_user)


def sha1_file(file_name):
    sha1sum = hashlib.sha1()
    with open(file_name, 'rb') as source:
        block = source.read(2 ** 16)
        while len(block) != 0:
            sha1sum.update(block)
            block = source.read(2 ** 16)

    return sha1sum.hexdigest()


def validate_download(filename, meta_data):
    if len(meta_data) != 0:
        # validate size
        file_size = os.path.getsize(filename)
        sha1 = sha1_file(filename)

        if meta_data[0] != file_size:
            raise ValidationError('Assertion failed.\n  Expect Size {}, got {}.'.format(meta_data[0], file_size))

        if meta_data[1] != sha1:
            raise ValidationError('Assertion failed.\n  Expect SHA1 {}, got {}.'.format(meta_data[1], sha1))

        print('File {} has passed the validation.'.format(os.path.basename(filename)))
    else:
        print('Failed to perform validation, invalid meta data')


def download_and_place_v2ray(version, filename, msg):
    print('Currently installed version: {}, {}...'.format(get_v2ray_version(), msg))

    meta_data = get_meta_data(version, filename)
    full_path = '/tmp/v2rayHelper/{}'.format(filename
                                             )
    download_file('https://github.com/v2ray/v2ray-core/releases/download/{}/{}'.format(version, filename), filename)
    validate_download(full_path, meta_data)
    extract_file(full_path, '/tmp/v2rayHelper/')

    # remove zip file
    remove_if_exists(full_path)

    return place_file(get_extracted_path(full_path, version))


def upgrader(filename, version, force=False):
    __init()

    if version != get_v2ray_version() or force:
        if force:
            print('You already installed the latest version, forced to upgrade')

        # download and place file
        download_and_place_v2ray(version, filename, 'upgrading')

        # restart v2ray
        v2ray_service('restart')
        print('Successfully upgraded to v2ray-{}'.format(version))
    else:
        print('You already installed the latest version')

    __cleanup()


def installer(filename, version):
    __init()

    # download and install
    installed_path = download_and_place_v2ray(version, filename, 'installing')

    # create soft link, for linux /usr/bin, bsd /usr/local/bin
    base_path = '/usr{}/bin'.format('/local' if os_is_bsd() else '')
    executables = ['v2ray', 'v2ctl']

    for file in executables:
        full_path = '{}/{}'.format(base_path, file)

        # delete old one
        if os.path.exists(full_path) or os.path.islink(full_path):
            os.unlink(full_path)

        # create symbol link
        os.symlink(installed_path + file, full_path)

    # add user
    add_user()

    # script
    install_start_script()
    enable_auto_start()

    # download and place the default config file
    conf = install_default_config_file()

    # start v2ray
    v2ray_service('start')

    # print message
    print('Successfully installed v2ray-{}'.format(info[1]))

    if conf is not None:
        print()
        print('v2ray is now bind on {}:{}'.format(get_ip(), conf[1]))
        print('uuid: {}'.format(conf[0]))
        print('alterId: {}'.format(64))

    __cleanup()


def mac_install(force):
    # check if brew is installed
    if is_command_exists('brew'):
        # already installed
        if not is_command_exists('v2ray') or force:
            # Install the official tap
            print('Install the official tap...')
            execute_external_command('brew tap v2ray/v2ray')

            # install v2ray
            print('Install v2ray...')
            execute_external_command('brew install v2ray-core')

            # set auto-start
            print('register v2ray to launch at login...')
            execute_external_command('brew services start v2ray-core')

            # print message
            print('Successfully installed v2ray')
        else:
            print('v2ray is already installed, use --force to force install')
    else:
        sys.exit('This script requires Homebrew')


def handler(signum, frame):
    print('\nKeyboard interrupt!!! Clean-up')
    remove_if_exists('/tmp/v2rayHelper')
    exit(1)


def print_help():
    print('Usage: {} [auto|install|upgrade] [--force]'.format(os.path.basename(sys.argv[0])))
    exit(0)


def parse_command_line_input():
    available_mode = ['auto', 'install', 'upgrade']

    argc = len(sys.argv)
    args = {'script_name': os.path.basename(sys.argv[0]), 'help': False, 'force': False, 'mode': 'auto'}

    if argc > 1:
        if sys.argv[1] == '--help':
            args['help'] = True
        else:
            if sys.argv[1] in available_mode:
                args['mode'] = sys.argv[1]
            else:
                args['help'] = True
        if argc > 2:
            if sys.argv[2] == '--force':
                args['force'] = True

    return args


def __init():
    # clean-up and create temp folder
    remove_if_exists('/tmp/v2rayHelper')
    mkdir('/tmp/v2rayHelper', 0o644)


def __cleanup():
    # delede temp folder
    remove_if_exists('/tmp/v2rayHelper')


if __name__ == "__main__":
    signal.signal(signal.SIGINT, handler)
    args = parse_command_line_input()
    install_status = is_command_exists('v2ray')

    if args['help']:
        print_help()
    try:
        operating_system = get_os_info()

        if os_is_supported():
            if os_is_nix():
                if os.getuid() == 0:
                    info = get_latest_version_from_api(*operating_system)
                    if args['mode'] == 'auto':
                        if install_status:
                            upgrader(*info)
                        else:
                            installer(*info)
                    elif args['mode'] == 'install':
                        if install_status is False or args['force'] is True:
                            installer(*info)
                        else:
                            sys.exit('v2ray is already installed, use --force to reinstall.')
                    elif args['mode'] == 'upgrade':
                        if install_status is False:
                            sys.exit('v2ray must be installed before you can upgrade it.')
                        else:
                            if args['force'] is True:
                                upgrader(*info, force=True)
                            else:
                                upgrader(*info)
                else:
                    # ask for root privileges
                    if is_command_exists('sudo'):
                        print('Re-lunching with root privileges...')
                        os.execvp('sudo', ['sudo', '/usr/bin/env', 'python3'] + sys.argv)
                    elif is_command_exists('su'):
                        print('Re-lunching with root privileges...')
                        os.execvp('su', ['su', '-c', ' '.join(['/usr/bin/env python3'] + sys.argv)])
                    else:
                        sys.exit('Sorry, cannot gain root privilege.')
            elif os_is_mac():
                mac_install(args['force'])

            # delete temp folder
            remove_if_exists('/tmp/v2rayHelper')
    except UnsupportedPlatform:
        sys.exit(
            'Unsupported platform: {0}/{1} ({2})'.format(platform.system(), platform.machine(), platform.version())
        )
    except ValidationError as e:
        sys.exit(str(e))
