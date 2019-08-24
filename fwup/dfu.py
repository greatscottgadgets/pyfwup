"""
DFU programming functionality.
"""

from __future__ import print_function

import re
import argparse
import collections
import struct
import sys
import time

import usb.core
import usb.util


from .core import FwupTarget
from .errors import BoardNotFoundError


class DFUError(IOError):
    """ Error representing a device-reported DFU error. """

    def __init__(self, code):
        # FIXME: covert the DFU error code to an error name
        super(DFUError, self).__init__("DFU error: {}".format(code))



class DFUTarget(FwupTarget):
    """ Class that represents a target device in DFU mode. """

    # Constants for fwup-util.
    FWUP_UTILITY_NAME = 'dfu-upload'
    FWUP_TARGET_NAME  = 'dfu'

    # DFU commands
    DFU_DETACH                         = 0
    DFU_DOWNLOAD                       = 1
    DFU_UPLOAD                         = 2
    DFU_GET_STATUS                     = 3
    DFU_CLEAR_STATUS                   = 4
    DFU_GET_STATE                      = 5
    DFU_ABORT                          = 6

    # DFU states.
    DFU_STATE_APP_IDLE                 = 0x00
    DFU_STATE_APP_DETACH               = 0x01
    DFU_STATE_DFU_IDLE                 = 0x02
    DFU_STATE_DFU_DOWNLOAD_SYNC        = 0x03
    DFU_STATE_DFU_DOWNLOAD_BUSY        = 0x04
    DFU_STATE_DFU_DOWNLOAD_IDLE        = 0x05
    DFU_STATE_DFU_MANIFEST_SYNC        = 0x06
    DFU_STATE_DFU_MANIFEST             = 0x07
    DFU_STATE_DFU_MANIFEST_WAIT_RESET  = 0x08
    DFU_STATE_DFU_UPLOAD_IDLE          = 0x09
    DFU_STATE_DFU_ERROR                = 0x0a

    # Misc constants.
    DFU_STATUS_LENGTH                  = 6

    # USB standard constants.
    DFU_DEVICE_CLASS                   = 0xFE
    DFU_DEVICE_SUBCLASS                = 0x01
    DFU_DESCRIPTOR_TYPE                = 0x21

    # 0 01 00001
    # ^           out
    #   ^^        class request
    #      ^^^^^  to interface
    USB_CLASS_OUT_REQUEST_TO_INTERFACE = 0b00100001

    # 1 01 00001
    # ^           in
    #   ^^        class request
    #      ^^^^^  to interface
    USB_CLASS_IN_REQUEST_TO_INTERFACE = 0b10100001



    @classmethod
    def __find_dfu_interface_on_device(cls, device):
        """
        Locates any DFU-compatible interfaces on any configuration the device has.

        Returns a 2-tuple with <configuration value>, <interface number> if a DFU interface
        exists on the device; or None, None if none exists.
        """

        # Check every interface of every configuration.
        for configuration in device:
            for interface in configuration:

                # Check to see if we match the USB spec's DFU class and subclass.
                matches_class    = interface.bInterfaceClass    == cls.DFU_DEVICE_CLASS
                matches_subclass = interface.bInterfaceSubClass == cls.DFU_DEVICE_SUBCLASS

                # If this matches both our class and subclass, it's a DFU device.
                # Return its interface number.
                if matches_class and matches_subclass:
                        return configuration.bConfigurationValue, interface.bInterfaceNumber

        return None, None


    @classmethod
    def __is_dfu_device(cls, device):
        """ Returns true iff the given pyusb device is DFU-capable. """

        _, interface = cls.__find_dfu_interface_on_device(device)
        return (interface is not None)


    @classmethod
    def find_dfu_devices(cls, *args, **kwargs):
        """
        Returns a list of USB devices currently detected in DFU mode.
        Accepts the same arguments as pyusb's usb.core.find(), allowing for specificity.
        """

        # Find all devices that have a DFU interface, and which meet our user's requirements.
        return usb.core.find(*args, find_all=True, custom_match=cls.__is_dfu_device, **kwargs)



    def __init__(self, *args, **kwargs):
        """ Creates a new class representing a DFU target.

        Accepts the same specifier arguments as pyusb's usb.core.find(); plus an index argument that gets
        the Nth available device.

        """

        # Default keyword argument support for py2.
        if 'index' not in kwargs:
            index = 0

        # Find a DFU device to work with.
        devices = list(self.find_dfu_devices())
        try:
            self.device = devices[index]
        except:
            raise BoardNotFoundError()

        # Determine which configuration and interface expose DFU functionality...
        self.configuration, self.interface = self.__find_dfu_interface_on_device(self.device)

        # ... and ensure the relevant configuration is active.
        try:
            self.device.set_configuration(self.configuration)
            self.device.detach_kernel_driver(self.interface)
        except:
            pass

        # Read the device's download parameters.
        self.__read_device_info()


    def __read_device_info(self):

        # FIXME: implement me!
        self.page_size = 2048



    def __dfu_out_request(self, request, value, data, timeout=5000):
        """ Convenience function that issues a DFU OUT control request to our device. """

        self.device.ctrl_transfer(self.USB_CLASS_OUT_REQUEST_TO_INTERFACE, request, value,
            self.interface, data, timeout)


    def __dfu_in_request(self, request, value, length, timeout=5000):
        """ Convenience function that issues a DFU IN control request, reading data from our device. """

        return self.device.ctrl_transfer(self.USB_CLASS_IN_REQUEST_TO_INTERFACE, request, value,
            self.interface, length, timeout)


    def __get_status(self):
        """ Retrieve the device's current DFU status. """

        # Grab and the DFU status...
        raw_status = self.__dfu_in_request(self.DFU_GET_STATUS, 0, self.DFU_STATUS_LENGTH)

        # ... and extract is component parts.
        status, poll_timeout_low, poll_timeout_high, state = struct.unpack("<BHBBx", raw_status)
        poll_timeout = (poll_timeout_high << 16) | poll_timeout_low

        return status, poll_timeout, state


    def __complete_command(self):
        """ Blocks until the given command completes, checking status. """

        while True:
            status, poll_timeout, state = self.__get_status()

            # If the the DFU device is in a finished state, break out.
            if state in (self.DFU_STATE_DFU_ERROR, self.DFU_STATE_DFU_DOWNLOAD_IDLE):
                break

            # Otherwise, wait for the provided poll timeout.
            if poll_timeout:
                time.sleep(poll_timeout / 1000)


        # Check to make sure the command completed correctly.
        if status:
            raise DFUError(status)



    def __raw_write_page(self, address, data, block_number=None):
        """
        Uploads a single page of data to the DFU target. On some targets, this requires that
        the relevant memory be erased before applying.
        """

        # If we don't have a block number, create one from the address of the page.
        if block_number is None:
            block_number = address // self.page_size

        # Download the firmware to the device...
        self.last_block_number = block_number
        self.__dfu_out_request(self.DFU_DOWNLOAD, block_number, data)

        # ... and wait for the command to complete.
        self.__complete_command()


    def __send_download_complete(self):
        """ Indicates that a DFU download is complete. """

        # Send an empty block write to indicate an end.
        try:
            self.__raw_write_page(0, b"", block_number=self.last_block_number + 1)
        except usb.core.USBError:
            # USB errors are acceptable here; as many devices detach here.
            pass


    def erase(self):
        pass


    def program(self, program_data, status_callback=None):
        """ Uploads a given program to the target DFU device. """

        for page_address in range(0, len(program_data), self.page_size):

            # Extract the page to be programmed...
            data_to_program = bytearray(program_data[page_address : page_address + self.page_size])

            # ... and download it to the device.
            self.__raw_write_page(page_address, data_to_program)

            # Issue our status callback to indicate our progress.
            if callable(status_callback):
                status_callback(page_address, len(program_data))


        # Notify the device that we're done programming.
        self.__send_download_complete()

        # Report that we're 100% programmed.
        if callable(status_callback):
            status_callback(len(program_data), len(program_data))


    def run_user_program(self):
        """ Runs the target user program. """
        pass

