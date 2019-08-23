"""
LPC43xx programming functionality.
"""

from __future__ import print_function

import struct

from .dfu import DFUTarget


class LPC43xxTarget(DFUTarget):
    """
    Class representing an LPC43xx in DFU mode.
    """

    # Constants for fwup-util.
    FWUP_UTILITY_NAME = 'lpc-upload'
    FWUP_TARGET_NAME = 'lpc43xx'

    # Default VID/PID for NXP DFU devices.
    VENDOR_ID  = 0x1fc9
    PRODUCT_ID = 0x000c

    def __init__(self, *args, **kwargs):
        """ Finds DFU devices that specifically match NXP's LPC VID/PID. """

        if 'idVendor' not in kwargs:
            kwargs['idVendor'] = self.VENDOR_ID
        if 'idProduct' not in kwargs:
            kwargs['idProduct'] = self.PRODUCT_ID

        super().__init__(*args, **kwargs)


    def program(self, program_data, status_callback=None):
        """ Uploads a program to the LPC43xx's RAM. """

        # Ensure that our program data is in a mutable byte format.
        program_data = bytearray(program_data)

        # Append our LPC DFU header.
        header = struct.pack(">BBH", 0xda, 0xff, len(program_data)) + (b"\xff" *12)
        program_data[0:0] = header

        # And call the main DFU functionality.
        super().program(program_data, status_callback)



