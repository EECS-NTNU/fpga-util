#!/usr/bin/env python3
import time
import argparse
import os
import subprocess
import sys
import pwd
import shutil
import signal
import re
from filelock import FileLock

mappingSearchPath = [ os.path.abspath(os.path.join(os.path.dirname(__file__), 'mapping')) ]

# MAKEFILE_EXTENSION -- DO NOT REMOVE!

def get_fpga_bridge_id(fpga):
    for entry in os.listdir('/sys/bus/pci/devices'):
        if re.match('^0000:' + re.escape(fpga['pci_id']) + ':[a-fA-F0-9]{2}\.[0-7]$', entry):
            bridgePath = os.path.abspath(os.path.realpath('/sys/bus/pci/devices/' + entry) + '/../')
            if (os.path.exists(bridgePath)):
                return os.path.basename(bridgePath)
    return None

def get_fpga_device_ids(fpga):
    result = []
    for entry in os.listdir('/sys/bus/pci/devices'):
        if re.match('^0000:' + re.escape(fpga['pci_id']) + ':[a-fA-F0-9]{2}\.[0-7]$', entry):
            result.append(entry)
    return result

def get_fpga_devs(fpga):
    def readUevent(path):
        if not os.path.exists(path + '/uevent'):
            return {}
        return {
            entry[0]: entry[1] for entry in [line.strip('\n\r ').split('=') for line in open(path + '/uevent', 'r').readlines()] if len(entry) >= 2
        }

    def xdmaResolver(path):
        xdmaDevs = []
        for f in ['resource', 'resource0', 'resource1']:
            if os.path.exists(path + '/' + f):
                xdmaDevs.append(path + '/' + f)
        path += '/xdma'
        if os.path.isdir(path):
            xdmaDevs.extend(['/dev/' + uevent['DEVNAME'] for uevent in [readUevent(path + '/' + entry) for entry in os.listdir(path) if os.path.isdir(path + '/' + entry)] if 'DEVNAME' in uevent and os.path.exists('/dev/' + uevent['DEVNAME'])])
        return xdmaDevs

    resolvers = {
        'xdma' : xdmaResolver
    }

    returnDevs = []
    fpgaDevices = get_fpga_device_ids(fpga)
    for fpgaDev in fpgaDevices:
        path = '/sys/bus/pci/devices/' + fpgaDev
        fpgaDevUevent = readUevent(path)
        if 'DRIVER' not in fpgaDevUevent or fpgaDevUevent['DRIVER'] not in resolvers:
            continue
        returnDevs.extend(resolvers[fpgaDevUevent['DRIVER']](os.path.realpath(path)))

    return returnDevs

def ownFpgaDevs(fpga, uid):
    pwRecord = pwd.getpwuid(uid)
    fpgaDevs = get_fpga_devs(fpga)
    for f in fpgaDevs:
        shutil.chown(f, user=pwRecord.pw_uid, group=pwRecord.pw_gid)

def xilinx_alveo_pciquirk(state, fpga, quiet = True):
    bridgeId = get_fpga_bridge_id(fpga)
    error = False
    if state == 0:
        if bridgeId is None:
            return False
        if not quiet:
            print('xilinx_alveo_pciquirk: setpci -s ' + bridgeId + ' COMMAND=0000:0100', flush=True)
        run = subprocess.run(['setpci', '-s', bridgeId, 'COMMAND=0000:0100'])
        error = error or run.returncode != 0
        if not quiet:
            print('xilinx_alveo_pciquirk: setpci -s ' + bridgeId + ' CAP_EXP+8.w=0000:0004', flush=True)
        run = subprocess.run(['setpci', '-s', bridgeId, 'CAP_EXP+8.w=0000:0004'])
        error = error or run.returncode != 0
        return not error
    elif state == 1:
        if bridgeId  is not None:
            deviceIds = get_fpga_device_ids(fpga)
            for deviceId in deviceIds:
                if os.path.exists('/sys/bus/pci/devices/' + bridgeId + '/' + deviceId + '/remove'):
                    try:
                        if not quiet:
                            print('xilinx_alveo_pciquirk: 1 > /sys/bus/pci/devices/' + bridgeId + '/' + deviceId + '/remove', flush=True)
                        open('/sys/bus/pci/devices/' + bridgeId + '/' + deviceId + '/remove', 'w').write('1\n')
                    except Exception:
                        error = True
            try:
                if not quiet:
                    print('xilinx_alveo_pciquirk: 1 > /sys/bus/pci/devices/' + bridgeId + '/rescan', flush=True)
                open('/sys/bus/pci/devices/' + bridgeId + '/rescan', 'w').write('1\n')
            except Exception:
                error = True
        else:
            try:
                if not quiet:
                    print('xilinx_alveo_pciquirk: 1 > /sys/bus/pci/rescan', flush=True)
                open('/sys/bus/pci/rescan', 'w').write('1\n')
            except Exception:
                error = True

        deviceIds = get_fpga_device_ids(fpga)
        for deviceId in deviceIds:
            if not quiet:
                print('xilinx_alveo_pciquirk: setpci -s ' + deviceId + ' COMMAND=0x02', flush=True)
            run = subprocess.run(['setpci', '-s', deviceId, 'COMMAND=0x02'])
            error = error or run.returncode != 0
        return not error
    return False

quirks = {
    'xilinx-alveo-quirk' : xilinx_alveo_pciquirk
}

lockDir = '/run/lock/fpga-util'
mainLock = '/run/lock/fpga-util.lock'
fileFpgaMapping = None

for f in mappingSearchPath:
    if os.path.exists(f):
        fileFpgaMapping = f
        break

if fileFpgaMapping is None:
    print("ERROR: could not find fpga mapping files", file=sys.stderr)
    exit(-1)

sudoUserId = os.getenv('SUDO_UID', default=False)
isAdmin = (os.getuid() == 0) and (sudoUserId is False)
userId = os.getuid() if sudoUserId is False else int(sudoUserId)

parser = argparse.ArgumentParser(description="FPGA Utils")
parser.add_argument("ids", default=[], nargs="*", type=str, help="FPGA ids (all if not specified)")
parser.add_argument("-l", "--list", help="list all FPGAs and their status", default=False, action="store_true")
parser.add_argument("-a", "--allocate", help="allocate FPGAs", default=False, action="store_true")
parser.add_argument("-f", "--flash", help="flash vivado bitstream to FPGAs", default=False, action="store_true")
parser.add_argument("-r", "--release", help="release FPGAs", default=False, action="store_true")
parser.add_argument("-d", "--devices", help="list devices attached to PCIe of currently allocated FPGAs", default=False, action="store_true")
parser.add_argument("-b", "--bitstream", help="use this bitstream for flashing", default=False)
parser.add_argument("--hwserver-bin", help="set hardware server executeable explicitly", default=None)
parser.add_argument("--vivado-bin", help="set vivado executable explicitly", default=None)
parser.add_argument("-q", "--quiet", help="sssshhh...", default=False, action="store_true")
if (isAdmin):
    parser.add_argument("--force", help="force actions", default=False, action="store_true")
args = parser.parse_args()


if args.flash:
    if args.bitstream is False or not os.path.isfile(args.bitstream):
        if not args.quiet:
            print('ERROR: a bitstream is required for flashing!', file=sys.stderr)
        exit(-1)

    args.bitstream = os.path.abspath(args.bitstream)

    if args.hwserver_bin is None:
        args.hwserver_bin = shutil.which('hw_server')
    if args.vivado_bin is None:
        args.vivado_bin = shutil.which('vivado')

    if args.hwserver_bin is None:
        if not args.quiet:
            print('ERROR: could not find Xilinx Hardware Server!', file=sys.stderr)
        exit(-1)
    if args.vivado_bin is None:
        if not args.quiet:
            print('ERROR: could not find Xilinx Vivado!', file=sys.stderr)
        exit(-1)

    args.vivado_bin = os.path.abspath(args.vivado_bin)
    args.hwserver_bin = os.path.abspath(args.hwserver_bin)

if (os.getuid() != 0):
    execvArgs  = ['/usr/bin/sudo', os.path.abspath(__file__)] + sys.argv[1:]
    if args.flash:
        execvArgs += ['--vivado-bin', args.vivado_bin, '--hwserver-bin', args.hwserver_bin]
    os.execv(execvArgs[0], execvArgs)

if not os.path.isdir(lockDir):
    os.makedirs(lockDir, exist_ok=True)

with FileLock(mainLock):
    fpgaMapping = {}
    for line in open(fileFpgaMapping, 'r').readlines():
        line = line.replace('\t', ' ').replace('  ',' ').strip('\n\r ')
        parts = line.split(' ')
        if len(parts) == 5:
            parts[4] = parts[4] if os.path.isabs(parts[4]) else (os.path.dirname(fileFpgaMapping) + '/' + parts[4])
            if os.path.isfile(parts[4]):
                if os.path.isfile(lockDir + '/' + parts[0]):
                    try:
                        usedBy = int(open(lockDir + '/' + parts[0], 'r').readlines()[0])
                    except Exception:
                        usedBy = False
                else:
                    usedBy = False
                fpgaMapping[parts[0]] = {
                    'serial': parts[0],
                    'pci_id': parts[1],
                    'quirk': parts[2],
                    'board' : parts[3],
                    'flash_tcl': parts[4],
                    'user_id' : usedBy,
                }
            else:
                print(f'ERROR: from configuration file {fileFpgaMapping} tcl script {parts[4]} was not found!', file=sys.stderr)

    if len(fpgaMapping) == 0:
        if not args.quiet:
            print('ERROR: could not find any FPGAs on the system!', file=sys.stderr)
        exit(-1)

    if (not args.flash and not args.allocate and not args.release and not args.devices):
        args.list = True

    if args.list:
        print(f'{"#":<3} {"Serial":<16} {"PCIe-ID":<10} {"Board":<12} {"Quirk":<22} {"Status":<10} {"User"}')
        for num, i in enumerate(fpgaMapping):
            fpga = fpgaMapping[i]
            fpgaStatus = 'free' if fpga['user_id'] is False else 'in use'
            userName = ''
            if fpga['user_id'] is not False and (isAdmin or fpga['user_id'] == userId):
                userName = pwd.getpwuid(fpga['user_id']).pw_name
            print(f'{num:<3} {fpga["serial"]:<16} {fpga["pci_id"]:<10} {fpga["board"]:<12} {fpga["quirk"]:<22} {fpgaStatus:<10} {userName}')

    if (not args.flash and not args.allocate and not args.release and not args.devices):
        exit(0)

    applyForce = isAdmin and args.force

    if applyForce and len(args.ids) == 0:
        args.ids = list(fpgaMapping.items())
    elif args.allocate and len(args.ids) == 0:
        args.ids = [f for f in fpgaMapping if fpgaMapping[f]["user_id"] is False]
    elif (args.release or args.flash or args.devices) and len(args.ids) == 0:
        args.ids = [f for f in fpgaMapping if fpgaMapping[f]["user_id"] == userId]

    filteredIds = []
    for i in args.ids:
        if i not in fpgaMapping:
            if not args.quiet:
                print(f"ERROR: device id {i} unknown!", file=sys.stderr)
        elif not applyForce and args.allocate and fpgaMapping[i]['user_id'] is not False:
            if not args.quiet:
                print(f"ERROR: device id {i} is in use!", file=sys.stderr)
        elif not applyForce and (args.release or args.flash or args.devices) and fpgaMapping[i]['user_id'] != userId:
            if not args.quiet:
                print(f"ERROR: device id {i} is not owned by you!", file=sys.stderr)
        else:
            filteredIds.append(i)
    args.ids = filteredIds

    if len(args.ids) == 0:
        if not args.quiet:
            print("ERROR: no devices available!", file=sys.stderr)
        exit(-1)

    if args.allocate:
        for i in args.ids:
            open(lockDir + '/' + fpgaMapping[i]["serial"], 'w').write(str(userId))
            ownFpgaDevs(fpgaMapping[i], userId)
            if not args.quiet:
                print(f'INFO: allocated device id {i} and changed ownership of attached devices', flush=True)
            else:
                print(i)


    if args.flash:
        def demote(uid, gid):
            def result():
                os.setgid(gid)
                os.setuid(uid)
            return result

        pwRecord = pwd.getpwuid(userId)
        vivadoEnv = os.environ.copy()
        vivadoEnv['HOME'] = pwRecord.pw_dir
        vivadoEnv['LOGNAME'] = pwRecord.pw_name
        vivadoEnv['USER'] = pwRecord.pw_name

        anyError = False
        anyInterrupts = False

        for i in args.ids:
            thisInterrupt = False
            thisError = False
            fpga = fpgaMapping[i]
            if fpga['quirk'] in quirks:
                if not args.quiet:
                    print(f'INFO: apply quirk for {fpga["quirk"]} on device id {i} before flashing', flush=True)
                if not quirks[fpga['quirk']](0, fpga, args.quiet):
                    if not args.quiet:
                        print(f'WARNING: could not apply quirk for device id {i}', file=sys.stderr)

            if not args.quiet:
                print(f'INFO: starting hardware server and vivado to flash device id {i}', flush=True)

            def signal_handler(sig, frame):
                if not args.quiet:
                    print('INFO: interrupt received, exiting gracefully...')
                thisInterrupt = True

            signal.signal(signal.SIGINT, signal_handler)
            signal.signal(signal.SIGTERM, signal_handler)

            pVivado = subprocess.Popen(
                [args.vivado_bin, '-mode', 'batch', '-nolog', '-nojournal', '-source', fpga['flash_tcl'], '-notrace', '-tclargs', fpga['serial'], fpga['pci_id'], fpga['board'], args.bitstream],
                preexec_fn=demote(pwRecord.pw_uid, pwRecord.pw_gid), env=vivadoEnv,
                stdout=(subprocess.DEVNULL if args.quiet else None), stderr=(subprocess.DEVNULL if args.quiet else None), stdin=subprocess.DEVNULL
            )

            pVivado.wait()

            signal.signal(signal.SIGINT, signal.default_int_handler)
            signal.signal(signal.SIGTERM, signal.SIG_DFL)

            if pVivado.returncode != 0:
                if not args.quiet:
                    print(f'ERROR: could not flash device id {i}', file=sys.stderr)
                thisError = True

            if fpga['quirk'] in quirks:
                if not args.quiet:
                    print(f'INFO: apply quirk for {fpga["quirk"]} on device id {i} after flashing', flush=True)
                if not quirks[fpga['quirk']](1, fpga, args.quiet):
                    if not args.quiet:
                        print(f'WARNING: could not apply quirk for device id {i}', file=sys.stderr)

            if not thisError:
                ownFpgaDevs(fpga, userId)
                if not args.quiet:
                    print(f'INFO: flashed bitstream to device id {i} and changed ownership of attached devices', flush=True)
                else:
                    print(i)

            if thisInterrupt or thisError:
                anyError = anyError or thisError
                anyInterrupts = anyInterrupts or thisInterrupt
                break

        if anyError or anyInterrupts:
            exit(-1)

    if args.release:
        for i in args.ids:
            if os.path.exists(lockDir + '/' + fpgaMapping[i]["serial"]):
                ownFpgaDevs(fpgaMapping[i], 0)
                os.unlink(lockDir + '/' + fpgaMapping[i]["serial"])
                if not args.quiet:
                    print(f'INFO: released device id {i} and changed ownership of attached devices', flush=True)
                else:
                    print(i)

    if args.devices:
        for i in args.ids:
            fpga = fpgaMapping[i]
            for f in get_fpga_devs(fpga):
                print(f)
