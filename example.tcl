set serial [lindex $argv 0]
set pci_id [lindex $argv 1]
set board [lindex $argv 2]
set bitstream [lindex $argv 3]

puts "Example TCL script called"
puts " Serial: ${serial}"
puts " PCIe ID: ${pci_id}"
puts " Board: ${board}"
puts " Bitstream: ${bitstream}"
exit 0
