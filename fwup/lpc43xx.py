"""
LPC43xx programming functionality.
"""

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

    # DFU header block size.
    BLOCK_SIZE  = 512
    HEADER_SIZE = 16


    def __init__(self, *args, **kwargs):
        """ Finds DFU devices that specifically match NXP's LPC VID/PID. """

        if 'idVendor' not in kwargs:
            kwargs['idVendor'] = self.VENDOR_ID
        if 'idProduct' not in kwargs:
            kwargs['idProduct'] = self.PRODUCT_ID

        # NXP's DFU bootloader claims to be in run-time mode but is actually in DFU mode.
        kwargs['detach'] = False

        super(LPC43xxTarget, self).__init__(*args, **kwargs)


    def program(self, program_data, status_callback=None):
        """ Uploads a program to the LPC43xx's RAM. """

        # Ensure that our program data is in a mutable byte format.
        program_data = bytearray(program_data)

        #
        # Append an LPC DFU header.
        #

        # Determine the number of total blocks, including this header.
        # This math rounds up to the next full block.
        program_size_blocks = (len(program_data) + (self.BLOCK_SIZE - self.HEADER_SIZE - 1)) // 512

        header = struct.pack("<BBH", 0xda, 0xff, program_size_blocks) + (b"\xff" *12)
        program_data[0:0] = header

        # And call the main DFU functionality.
        super(LPC43xxTarget, self).program(program_data, status_callback)



