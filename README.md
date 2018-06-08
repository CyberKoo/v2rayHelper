# v2rayHelper
v2rayHelper is a python script. It provides an easy way to install or upgrade v2ray.

## Requirements
* python3 (3.4+)
* systemd based Linux or FreeBSD

## Tested platform
| Operating system | Version     | Architecture | Supported                | Note                 |
| :-----------: |:-------------: | :----------: | :----------------------: | :------------------: |
| CentOS        | 7.5            | AMD64        | :heavy_check_mark:       |                      |
| CentOS        | 6.x            | X86/AMD64    | :heavy_exclamation_mark: | SysV                 |
| Ubuntu        | 18.10          | AMD64        | :heavy_check_mark:       |                      |
| Ubuntu        | 18.04 LTS      | AMD64        | :heavy_check_mark:       |                      |
| Ubuntu        | 17.10          | X86/AMD64    | :heavy_check_mark:       |                      |
| Ubuntu        | 16.04 TLS      | X86/AMD64    | :heavy_check_mark:       |                      |
| Ubuntu        | 14.04 LTS      | X86/AMD64    | :heavy_exclamation_mark: | Upstart              |
| Debian        | 9 Stretch      | AMD64        | :heavy_check_mark:       |                      |
| Debian        | 8 Jessie       | X86/AMD64    | :heavy_check_mark:       |                      |
| Arch Linux    | N/A            | ARM32        | :heavy_check_mark:       | Raspberry Pi 2 B+    |
| OpenSUSE      | Leap 15.0      | AMD64        | :heavy_check_mark:       |                      |
| OpenSUSE      | Tumbleweed     | X86/AMD64    | :heavy_check_mark:       | 2018.05.30           |
| FreeBSD       | 11.1           | AMD64        | :heavy_check_mark:       |                      |
| FreeBSD       | 10.4           | AMD64        | :heavy_check_mark:       |                      |
| OpenDSD       | 6.2            | AMD64        | :x:                      |                      |
| MacOS         | 10.13.5        | AMD64        | :heavy_check_mark:       | Via Homebrew         |

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
python3 v2rayHelper.py install
```

#### Force install v2ray
```shell
python3 v2rayHelper.py install --force
```

#### Upgrade v2ray
This command requires v2ray to be already installed.
```shell
python3 v2rayHelper.py upgrade
```

## License
[![License: GPL v3](https://img.shields.io/badge/License-GPL%20v3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
