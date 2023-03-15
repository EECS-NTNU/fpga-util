if { $argc == 4 } {
	set serial [lindex $argv 0]
	set bitstream [lindex $argv 3]

	set_param labtools.enable_cs_server false

	open_hw_manager
	connect_hw_server -url localhost:3121 -allow_non_jtag
	open_hw_target localhost:3121/xilinx_tcf/Xilinx/${serial}A
	set_property PROGRAM.FILE ${bitstream} [get_hw_devices xcu280_u55c_0]
	program_hw_devices [get_hw_devices xcu280_u55c_0]
	exit 0
}
exit 1
