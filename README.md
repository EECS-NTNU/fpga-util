# fpga-util.py

This helper script is used at NTNU in our clusters to manage multiple FPGAs in a multi user environment. It is designed so that unpriviliged users can allocate FPGAs, flash their bitstreams on them and release the FPGAs when they are done.

**WARNING:** this script does not protect the system from any further actions of the user that might compromise the system. In an untrusted environment it is important to thoroughly check the bitstreams before they are flashed to the FPGAs or allow only to flash bitstreams from a trusted implementation flow!

# Install / Uninstall

```bash
# This will create /usr/local/bin/fpga-util.py and /etc/fpga-util for configs
sudo make PREFIX=/usr/local/bin CONFIG_PREFIX=/etc install

# This will remove the installed files and folders
sudo make uninstall
```

**IMPORTANT:** to allow unpriviliged users (users without sudo) to use this script, one needs to adjust the sudoers file as follows:
```text
## FPGA-Utils
Cmnd_Alias FPGA_UTIL = /usr/local/bin/fpga-util.py

# Allow all users access to the FPGAs through the managing fpga-utils scripts
ALL     ALL=(root)      NOPASSWD: FPGA_UTIL

# OR allow all users in the fpga group to  access the FPGAs through the managing fpga-utils scripts
# %fpga     ALL=(root)      NOPASSWD: FPGA_UTIL
```

# Configuration

The main configuration file is the mapping file which contains per line the following space separated fields: Serial, PCIe id, Quirk, Board and TCL. The  provided example looks like this:

```text
DUMMY0 81 none u280 example.tcl
DUMMY1 01 none u250 example.tcl
```

### Serial

This must be a **unique** identification of the FPGA. It is passed to the tcl script. In the provided `u250.tcl` and `u280.tcl` scripts the serial is the JTAG serial number of the FPGAs (without the trailing 'A') to flash the FPGAs via their JTAG interface. But it can be anything for other flashing scripts.

### PCIe id

This is the PCIe id of the PCI root complex which the FPGA is connected to. It is used in the provided quirk to decouple the PCIe device before flashing and rescan the PCIe interface after flashing to detect new devices and probe the appropriate drivers. It is also used to identify connected devices for the `-d` option.

### Quirk

This is a quirk identifier that is applied before and after flashing. This helps to execute some predefined actions that are necessary to enable successfull flashing like decoupling attached devices or rescan for new devices. Currently there is one quirk implemented which has the name `xilinx-alveo-quirk` and enables flashing the u250 and u280 devices outside of the Vitis flow.

### Board

This is just the name of the board that this line belongs to. E.g. u250 or u280 or any other name. It is only used for the listing but is also passed to the tcl sccript.

### TCL

This is the TCL script that is invoked with Vivado to flash the FPGA. It is passed the serial, pcie id and board as parameter. For the none Vitis flow the `u250.tcl` and `u280.tcl` are provided to flash the FPGAs via JTAG. These scripts expect the serial to be the JTAG serial without the trailing 'A'! Provide your own script here if you are using another bitstream flashing approach.

# Usage

```text
usage: fpga-util.py [-h] [-l] [-a] [-f] [-r] [-d] [-b BITSTREAM]
                    [--hwserver-bin HWSERVER_BIN] [--vivado-bin VIVADO_BIN]
                    [-q]
                    [ids ...]

FPGA Utils

positional arguments:
  ids                   FPGA ids (all if not specified)

options:
  -h, --help            show this help message and exit
  -l, --list            list all FPGAs and their status
  -a, --allocate        allocate FPGAs
  -f, --flash           flash vivado bitstream to FPGAs
  -r, --release         release FPGAs
  -d, --devices         list devices attached to PCIe of currently allocated
                        FPGAs
  -b BITSTREAM, --bitstream BITSTREAM
                        use this bitstream for flashing
  --hwserver-bin HWSERVER_BIN
                        set hardware server executeable explicitly
  --vivado-bin VIVADO_BIN
                        set vivado executable explicitly
  -q, --quiet           sssshhh...
```

A typical usage looks like this:
```bash
fpga-util.py -a fpga0-serial
fpga-util.py -f -b bitstream.bit fpga0-serial
# Your FPGA should be flashed now do your stuff
fpga-util.py -r fpga0-serial
```


# TODOs

Currently this script executes as root the hw_server and vivado to flash the FPGAs. This requires a lock so that only one user can do this at a time. It would make more sense when allocating an FPGA that not only the attached devices from the FPGA take ownership of the user but also the JTAG interface from the FPGA receives the users ownership. This would enable executing the hw_server and vivado from the user context instead of root since the user has read and write permissions to use the JTAG interface. Somebody should do this in the future...
