# v2rayHelper
v2rayHelper is a python script. It provides an easy way to install or upgrade v2ray.

## Requirements
* Python3.4 or above

## Tested platform
| Operating system | Version     | Architecture | Supported                | Note                 |
| :-----------: |:-------------: | :----------: | :----------------------: | :------------------: |
| CentOS        | 7.0            | AMD64        | :heavy_check_mark:       |                      |
| CentOS        | 6.0            | X86/AMD64    | :heavy_exclamation_mark: | SysV                 |
| Ubuntu        | 18.04          | X86/AMD64    | :heavy_check_mark:       |                      |
| Ubuntu        | 14.04 LTS      | X86/AMD64    | :heavy_exclamation_mark: | Upstart              |
| Debian        | 8  / 9         | AMD64        | :heavy_check_mark:       |                      |
| Arch Linux    | N/A            | ARM32        | :heavy_check_mark:       | Raspberry Pi 2 B+    |
| OpenSUSE      | Leap 15.0      | AMD64/Aarch64| :heavy_check_mark:       |                      |
| OpenSUSE      | Tumbleweed     | X86/AMD64    | :heavy_check_mark:       | 2018.05.30           |
| FreeBSD       | 11.2 / 10.4    | AMD64        | :heavy_check_mark:       |                      |
| OpenDSD       | 6.2            | AMD64        | :heavy_check_mark:       |                      |
| MacOS         | 10.13.5        | AMD64        | :heavy_check_mark:       | Via Homebrew         |
| Windows       | 10 1809        | X86/AMD64    | :heavy_exclamation_mark: | Pre-release          |

## Usage
### Download file from github
```shell
wget 'https://raw.githubusercontent.com/waf7225/v2rayHelper/master/v2rayHelper.py'
```

### Auto mode
The following command will automatically install v2ray if not installed, or upgrade existing version if a newer version is available.
```shell
python3 v2rayHelper.py
```

### Manual mode

#### Install v2ray
```shell
python3 v2rayHelper.py --install
```

#### Force install v2ray
```shell
python3 v2rayHelper.py --install --force
```

#### Upgrade v2ray
This command requires v2ray to be already installed.
```shell
python3 v2rayHelper.py --upgrade
```

#### Remove v2ray
This command will remove installed v2ray.
```shell
python3 v2rayHelper.py --remove
```

## License
[![License: GPL v3](https://img.shields.io/badge/License-GPL%20v3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
