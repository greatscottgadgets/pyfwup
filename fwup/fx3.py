# This file is part of pyfwup.
""" Programmer definition for loading images to the Cypress FX3 bootloader. """

import time
import struct

import usb
import usb.core

from collections import OrderedDict

from .core import FwupTarget
from .errors import BoardNotFoundError, ProgrammingFailureError

# USB identifiers for the target device.
TARGET_VID     = 0x04b4
TARGET_PID     = 0x00f3

# Basic comms parameters for USB comms.
USB_REQUEST_TIMEOUT = 5000

# The maximum amount of data that should be stuck into a USB request.
USB_REQUEST_MAX_SIZE = 2048


class FX3Target(FwupTarget):
    """ Class that allows one to program an FX3 bootloader target. """

    # Constants for fwup-util.
    FWUP_UTILITY_NAME = 'fx3load'
    FWUP_TARGET_NAME = 'fx3'

    # Basic protocol details.
    VENDOR_REQUEST_UPLOAD = 0xa0


    def __init__(self, wait=True, fast_mode=False, *args, **kwargs):
        """ Creates a new connection to a given micronucleus bootloader. """

        vid = kwargs.get('idVendor', default=TARGET_VID)
        pid = kwargs.get('idProduct', default=TARGET_PID)

        # Try to find an FX3 device in bootloader mode.
        self.device = usb.core.find(idVendor=vid, idProduct=pid)
        if self.device is None:
            raise BoardNotFoundError()


    def _firmware_request(self, address, length_or_data, is_in=False):
        """ Transfers chunks of firmware to or from the device. """

        # Issue a vendor request to the device, carrying the address in its index/value.
        request_type = (usb.ENDPOINT_IN if is_in else usb.ENDPOINT_OUT) | usb.TYPE_VENDOR | usb.RECIP_DEVICE

        index = address >> 16
        value = address & 0xFFFF

        return self.device.ctrl_transfer(request_type, self.VENDOR_REQUEST_UPLOAD, value, index, length_or_data, timeout=USB_REQUEST_TIMEOUT)


    def _read_firmware_chunk(self, address, length):
        """ Read back a chunk of firmware from the device's memory. """
        return self._firmware_request(address, length, is_in=True)


    def _upload_firmware_chunk(self, address, data):
        """ Uploads a chunk of firmware to the device. """
        self._firmware_request(address, data, is_in=False)


    def _upload_firmware(self, address, data):
        """ Uploads a chunk of firmware to the device. """

        to_upload = data[:]

        while to_upload:

            # Break the firmware to upload into maximum-size chunks..
            chunk = to_upload[0:USB_REQUEST_MAX_SIZE]
            del to_upload[0:USB_REQUEST_MAX_SIZE]

            # ... and upload them chunk-by-chunk.
            self._upload_firmware_chunk(address, chunk)
            address += len(chunk)


    def _print_target_info(self, print_function):
        """ Prints information about the relevant board, if possible."""

        # Inject a language ID so we can interact with the device.
        self.device._langids = (0,)

        print_function("    Serial number: {}".format(self.device.serial_number))
        print_function("    Product: {}".format(self.device.product))
        print_function("    Manufacturer: {}".format(self.device.manufacturer))
        print_function("    Device revision: {}.{}".format(self.device.bcdDevice >> 8, self.device.bcdDevice & 0xFF))



    @staticmethod
    def _parse_program_data(program_data):

        program_chunks = OrderedDict()
        remaining_data = bytearray(program_data)

        # Read our program header.
        if program_data[0:2] != b"CY":
            raise ValueError("The provided file does not appear to be a Cypress image file.")
        del remaining_data[0:4]

        # Parse our cypress image data for as long as data potentially remains.
        while len(remaining_data) >= 8:

            # Extract the first eight bytes of the stream, which should contain two words:
            # the address of the following data chunk, and its length.
            header = remaining_data[0:8]
            size, address = struct.unpack("<II", header)
            del remaining_data[0:8]

            # Convert our size from a size-in-bytes to a size-in-words.
            size *= 4

            # A chunk of raw data of the size specified follows the little header.
            if len(remaining_data) < size:
                raise EOFError("a chunk header specified {} should be read; but only {} were remaining".format(
                        size, len(remaining_data)))

            # Grab the chunk, and move on to the next set of data.
            program_chunks[address] = remaining_data[0:size]
            del remaining_data[0:size]

        return program_chunks


    def erase(self):
        """ Erases the board's program flash. """
        print("Configuration is volatile; erase skipped.")


    def size_to_program(self, program_data):
        """ Computes the total size of the data to be programmed. """
        size = 0

        if isinstance(program_data, OrderedDict):
            chunks_to_program  = program_data
        else:
            chunks_to_program  = self._parse_program_data(program_data)

        # Summarize each of the chunks to be programmed.
        for _, data in chunks_to_program.items():
            size += len(data)

        return size


    def program(self, program_data, status_callback=None):
        """ Programs a given binary program to the microcontroller's flash memory. """

        # Split the program into the various sparse chunks to be uploaded...
        chunks_to_program = self._parse_program_data(program_data)
        total_size = self.size_to_program(chunks_to_program)

        # ... and program each chunk.
        size_written = 0
        for address, data in chunks_to_program.items():
            self.last_address = address
            self._upload_firmware(address, data)

            size_written += len(data)
            status_callback(size_written, total_size)


    def run_user_program(self):
        """ Requests that the bootloader start the user programer. """
        self._upload_firmware_chunk(self.last_address, b"")



