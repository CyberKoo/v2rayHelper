#!/usr/bin/env python3
import datetime
import fileinput
import os
import platform
import random
import shutil
import signal
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


def replace_content_in_file(filename, replace_pair):
    with fileinput.FileInput(filename, inplace=True) as file:
        for line in file:
            for replace in replace_pair:
                line = line.replace(replace[0], replace[1])

            print(line, end='')
    file.close()


def closure_try(__try, __except, __on_failure):
    try:
        return __try()
    except __except:
        return __on_failure()


def is_command_exists(command):
    def _try():
        subprocess.check_call('type {}'.format(command), shell=True, stderr=subprocess.DEVNULL,
                              stdout=subprocess.DEVNULL)
        return True

    def __on_failure():
        return False

    return closure_try(_try, subprocess.CalledProcessError, __on_failure)


def which_command_exists(commands):
    if is_collection(commands):
        for command in commands:
            if is_command_exists(command):
                return command
        return None
    else:
        raise TypeError


def is_collection(arg):
    return True if hasattr(arg, '__iter__') and not isinstance(arg, (str, bytes)) else False


def os_is(os_name):
    if is_collection(os_name):
        return True if platform.system().lower() in [x.lower() for x in os_name] else False
    else:
        return platform.system().lower() == os_name.lower()


def get_os():
    return '{0}/{1} ({2})'.format(platform.system(), platform.machine(), platform.version())


def get_v2ray_path(name=None):
    process_name = name if name is not None else 'v2ray'
    return subprocess.check_output('which {}'.format(process_name), shell=True, stderr=subprocess.DEVNULL) \
        .rstrip().decode("utf-8")


def get_v2ray_version():
    def _try():
        command = '{} --version'.format(get_v2ray_path())
        version = subprocess.check_output(command, shell=True).decode("utf-8").split()

        return version[1]

    def __on_failure():
        return None

    return closure_try(_try, subprocess.CalledProcessError, __on_failure)


def get_download_url(version, file):
    return 'https://github.com/v2ray/v2ray-core/releases/download/{}/{}'.format(version, file)


def is_systemd():
    return os.path.exists('/run/systemd/system') and os.path.isdir('/run/systemd/system')


def v2ray_service(command):
    if is_systemd():
        subprocess.check_call('systemctl {} v2ray'.format(command), shell=True)


def get_os_info():
    system = platform.system()
    arch = platform.architecture()[0][0:2]
    machine = platform.machine()

    standard_os = ['Linux', 'FreeBSD']
    standard_arch = ['X86_64', 'I386']
    arm_arch32 = ['armv7l', 'armv7', 'armv7hf', 'armv7hl']
    arm_arch64 = ['armv8']

    if system in standard_os:
        if machine not in standard_arch:
            if machine in arm_arch32:
                arch = 'arm'
            elif machine in arm_arch64:
                arch = 'arm64'

        return [system.lower(), arch, platform.architecture()[0], machine]

    raise UnsupportedPlatform


def get_latest_version_from_api(os, arch, arch_1, machine):
    api_url = 'https://api.github.com/repos/v2ray/v2ray-core/releases/latest'

    with urllib.request.urlopen(api_url) as response:
        json_response = json.loads(response.read().decode('utf8'))
        pre_release = '(pre release)' if json_response['prerelease'] is True else ''
        latest_version = json_response['tag_name']

        print('Hi there, the latest version of v2ray is {} {}'.format(latest_version, pre_release))
        print('Operating system: {}-{} ({})'.format(os, arch_1, machine))

        position = []
        for assets in json_response['assets']:
            position.append(assets['name'])

            if assets['name'].find('{}-{}'.format(os, arch)) != -1:
                return [assets['name'], latest_version]

        raise UnsupportedPlatform('{}-{} is not supported'.format(os, arch))


def download_file(url, file_name=None):
    base_name = os.path.basename(urlparse(url).path)

    if file_name is None:
        file_name = base_name

    temporary_file = '{}.{}'.format(file_name, 'v2tmp')

    # delete temp file
    if os.path.exists(temporary_file):
        os.remove(temporary_file)

    start_time = time.time()

    # print('Downloading: {}'.format(url))
    def __report_hook(block_num, block_size, total_size):
        def __format_size(size):
            n = 0
            unit = {0: '', 1: 'K', 2: 'M', 3: 'G', 4: 'T'}

            while size > 1024:
                size /= 1024
                n += 1

            return '{:6.2f} '.format(size) + unit[n] + 'B'

        read_so_far = block_num * block_size
        if total_size > 0:
            duration = int(time.time() - start_time)
            progress_size = int(block_num * block_size)
            speed = progress_size / duration if duration != 0 else 1
            percent = read_so_far * 1e2 / total_size
            estimate = int(total_size / speed) if speed != 0 else 0
            if percent > 100.00:
                percent = 100.00

            sys.stdout.write(
                "\rFetching: {:<25} {:5.2f}% {:>15} {:>15}/s {:>15s} {:<10}".format(base_name, percent,
                                                                                    __format_size(total_size),
                                                                                    __format_size(speed), str(
                        datetime.timedelta(seconds=estimate)), 'ETA')
            )

            if read_so_far >= total_size:  # near the end
                sys.stdout.write("\n")
        else:  # total size is unknown
            # TODO format output
            sys.stdout.write("\r read {}".format(read_so_far))

        sys.stdout.flush()

    urllib.request.urlretrieve(url, temporary_file, __report_hook)
    os.rename(temporary_file, file_name)


def extract_file(path, output):
    with zipfile.ZipFile(path, "r") as zip_ref:
        zip_ref.extractall(output)
    zip_ref.close()

    # remove zip file
    os.remove(path)


def place_file(path_from):
    install_path = ['/opt/v2ray/', '/usr/local/v2ray/']
    executables = ['v2ray', 'v2ctl']

    path_to = install_path[0]
    for path in install_path:
        if os.path.exists(path):
            path_to = path

    # remove old file
    if os.path.exists(path_to):
        shutil.rmtree(path_to)

    # move downloaded file to path_to
    shutil.move(path_from, path_to)

    # remove executable permission
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


# TODO add script for systemd, openrc, ...
def install_start_script():
    if os_is('linux'):
        # create systemd file or rc.d
        if is_systemd():
            download_file('https://raw.githubusercontent.com/waf7225/v2rayHelper/master/misc/v2ray.service',
                          'v2ray.service')

            shutil.move('./v2ray.service', '/etc/systemd/system/v2ray.service')
        else:
            # todo add support for legacy init scripts
            pass
    elif os_is('freebsd'):
        pass


def install_default_config_file():
    conf_dir = None

    if os_is('linux'):
        conf_dir = '/etc/v2ray'
    elif os_is('freebsd'):
        conf_dir = '/usr/local/etc/v2ray'

    if conf_dir is not None:
        # create default configuration file path
        if not os.path.exists(conf_dir):
            os.mkdir(conf_dir, 0o755)

        # download config file
        download_file('https://raw.githubusercontent.com/waf7225/v2rayHelper/master/misc/config.json',
                      'config.json')
        shutil.move('config.json', '{}/config.json'.format(conf_dir))

        replace = [str(uuid.uuid4()), str(random.randint(50000, 65535))]
        replace_content_in_file('{}/config.json'.format(conf_dir), [
            ['dbe16381-f905-4b88-946f-dfc21ed9be29', replace[0]],
            ['12345', replace[1]]
        ])

        return replace

    return None


def add_user(_user_ame=None):
    name = _user_ame if _user_ame is not None else 'v2ray'

    def _try_group():
        import grp
        grp.getgrnam(name)

    def _try_user():
        import pwd
        pwd.getpwnam(name)

    def _try_add_group():
        print('Group {} does not exist.'.format(name))
        subprocess.check_output('groupadd {}'.format(name), shell=True, stderr=subprocess.DEVNULL)

    def _try_add_user():
        print('Group {} does not exist.'.format(name))
        create_user = 'useradd {0} -md /var/lib/{0} -s /sbin/nologin -g {0}'.format(name)
        subprocess.check_output(create_user, shell=True, stderr=subprocess.DEVNULL)

    # add group
    closure_try(_try_group, KeyError, _try_add_group)

    # add user
    closure_try(_try_user, KeyError, _try_add_user)


def print_installed_version(msg):
    print('Currently installed version: {}, {}...'.format(get_v2ray_version(), msg))


def updater(filename, version, force=False):
    if version != get_v2ray_version() or force:
        if force:
            print('You already installed the latest version, force to update')
        print_installed_version('updating')

        download_file(get_download_url(version, filename), filename)
        extract_file(filename, '.')
        place_file(get_extracted_path(filename, version))

        # restart v2ray
        v2ray_service('restart')
        print('Successfully updated to v2ray-{}'.format(version))
    else:
        print('You already installed the latest version')


def installer(filename, version):
    print_installed_version('installing')

    download_file(get_download_url(version, filename), filename)
    extract_file(filename, '.')
    installed_path = place_file(get_extracted_path(filename, version))

    # create soft link
    link = ['/usr/bin/', ['v2ray', 'v2ctl']]

    # for FreeBSD
    if os_is('freebsd'):
        link[0] = '/usr/local/bin/'

    for file in link[1]:
        full_path = link[0] + file

        # delete old one
        if os.path.exists(full_path) or os.path.islink(full_path):
            os.unlink(full_path)

        # create symbol link
        os.symlink(installed_path + file, full_path)

    install_start_script()

    # download and place the default config file
    conf = install_default_config_file()

    # add user
    add_user()

    # start v2ray
    v2ray_service('start')
    print('Successfully installed v2ray-{}'.format(info[1]))
    print()
    print('v2ray is now bind on 0.0.0.0:{}'.format(conf[1]))
    print('uuid: {}'.format(conf[0]))


def handler(signum, frame):
    print('\nKeyboard interrupt!!! Clean-up')
    for file in Path('.').glob('*.v2tmp'):
        file.unlink()
    exit(1)


def print_help():
    print('Usage: {} [auto|install|update] [--force]'.format(os.path.basename(sys.argv[0])))
    exit(0)


def command_line_parser():
    available_mode = ['auto', 'install', 'update']
    args = {'script_name': os.path.basename(sys.argv[0]), 'help': False, 'force': False, 'mode': 'auto'}

    if len(sys.argv) > 1:
        if sys.argv[1] == '--help':
            args['help'] = True
        else:
            if sys.argv[1] in available_mode:
                args['mode'] = sys.argv[1]
            else:
                args['help'] = True

        if len(sys.argv) > 2:
            if sys.argv[2] == '--force':
                args['force'] = True

    return args


if __name__ == "__main__":
    signal.signal(signal.SIGINT, handler)
    args = command_line_parser()
    install_status = is_command_exists('v2ray')

    if args['help']:
        print_help()
    try:
        operating_system = get_os_info()

        if os_is(['linux', 'freebsd']):
            if os.getuid() == 0:
                info = get_latest_version_from_api(*operating_system)
                if args['mode'] == 'auto':
                    if install_status:
                        updater(*info)
                    else:
                        installer(*info)
                elif args['mode'] == 'install':
                    if install_status is False or args['force'] is True:
                        installer(*info)
                    else:
                        sys.exit('v2ray is already install, use --force to reinstall.')
                elif args['mode'] == 'update':
                    if install_status is False:
                        sys.exit('v2ray must be installed before you can update it.')
                    else:
                        if args['force'] is True:
                            updater(*info, True)
                        else:
                            updater(*info)
            else:
                # ask for root privileges
                if is_command_exists('sudo'):
                    print('You need root privileges to run this script, re-lunching...')
                    os.execvp('sudo', ['sudo', '/usr/bin/env', 'python3'] + sys.argv)
                elif is_command_exists('su'):
                    print('You need root privileges to run this script, re-lunching...')
                    os.execvp('su', ['su', '-c', ' '.join(['/usr/bin/env python3'] + sys.argv)])
                else:
                    sys.exit('Sorry, cannot gain root privilege')
    except UnsupportedPlatform:
        sys.exit('Unsupported platform: {}'.format(get_os()))
