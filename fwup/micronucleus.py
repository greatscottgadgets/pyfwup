import time
import struct

import usb
import usb.core

from .core import FwupTarget
from .errors import BoardNotFoundError, ProgrammingFailureError

MICRONUCLEUS_VID     = 0x16d0
MICRONUCLEUS_PID     = 0x0753
MICRONUCLEUS_TIMEOUT = 1000


class MicronucleusBoard(FwupTarget):
    """ Class that allows one to program a Micronucleus bootloader target. """

    # Constants for fwup-util.
    FWUP_UTILITY_NAME = 'microprog'
    FWUP_TARGET_NAME = 'micronucleus'


    #
    # USB protocol data.
    #

    # Request number for receiving MicroNucleus information.
    REQUEST_GET_INFO = 0

    # Request to write a page of data to the target bootloader.
    # For v1 clients, this request has a body that contains a page worth of data.
    # For v2 clients, this sets the address of the relevant page, but carries no body.
    # v2 clients instead provide the data using WRITE_WORD requests.
    REQUEST_WRITE_PAGE = 1

    # Request for erasing the device's user flash.
    REQUEST_ERASE_FLASH = 2

    # Request that writes a word of data to the target.
    # Used primarily for v2 micronucleus bootloaders.
    REQUEST_WRITE_DWORD = 3

    # Request that the bootloader jump to the user application.
    REQUEST_START_APPLICATION = 4


    #
    # AVR program data.
    #
    AVR_LONG_JUMP_OPCODE = 0x940c
    AVR_RJMP_OFFSET_MASK = 0x0fff
    AVR_RJMP_OPCODE_MASK = 0xf000
    AVR_RJMP_OPCODE      = 0xc000
    AVR_RJMP_REACH_BYTES = 0x2000

    #
    # Mapping that translates signatures to AVR names.
    #
    # TODO: enumerate more of the devices that are supported by micronucleus
    AVR_NAMES = {
        0x930c: "ATtiny84",
        0x930b: "ATtiny85",
    }


    @staticmethod
    def _print_preconnect_info(print_function):
        print_function("Plug the target board in now.")
        print_function("If the board is already plugged in, you may need to unplug and replug it before it will be found.")



    def __init__(self, wait=True, fast_mode=False, *args, **kwargs):
        """ Creates a new connection to a given micronucleus bootloader. """

        self.target_vid = kwargs.get('idVendor', default=MICRONUCLEUS_VID)
        self.target_pid = kwargs.get('idProduct', default=MICRONUCLEUS_PID)
        self.fast_mode = fast_mode

        # Attempt to grab a connection to the device.
        self._try_connect(wait=wait)

        # Otherwise, use our USB connection to initialize ourselves.
        self._populate_info_from_device()


    def _try_connect(self, wait=True, post_connect_delay=0.5):
        """ Attempts to connect to a given micronucleus device. Useful for both connecting and reconnecting."""

        self.device = None

        # Loop until we've found a micronucleus device.
        while (not self.device) and wait:

            # Try to find a micronucleus bootloader.
            candidate = usb.core.find(idVendor=self.target_vid, idProduct=self.target_pid)

            #	If this device
            if self._validate_device_compatibility(candidate):
                self.device = candidate

        # For systems like Linux, we'll need a small post-connect delay to allow udev to catch up
        # if the device was just plugged in. Otherwise, the device may still have its initial perms.
        time.sleep(post_connect_delay)

        # If we couldn't find a board (i.e. if wait wasn't set), error out.
        if self.device is None:
            raise BoardNotFoundError()


    def reconnect(self, wait=True):
        """ Attempts to reconnect to the given board. """
        self._try_connect(wait=wait)


    @classmethod
    def _validate_device_compatibility(cls, candidate):
        """ Returns true iff the given pyUSB device is a a micronucleus board we can program. """

        if candidate is None:
            return False

        # Return true if this device speaks the v1 or v2 protocol.
        return (candidate.bcdDevice >> 8) <= 2


    def _request_in(self, number, length, index=0, value=0, timeout=MICRONUCLEUS_TIMEOUT):
        """ Requests data from the Micronucleus device. """

        # Prepare the metadata that identifies how we're communicating...
        type_data = usb.ENDPOINT_IN | usb.TYPE_VENDOR | usb.RECIP_DEVICE

        # ... and use it to perform our core control request.
        return self.device.ctrl_transfer(type_data, number, index, value, length, timeout=timeout)


    def _request_out(self, number, data=None, value=0, index=0, timeout=MICRONUCLEUS_TIMEOUT):
        """ Issues data to the Micronucleus device, or issues a command without data. """

        # Prepare the metadata that identifies how we're communicating...
        type_data = usb.ENDPOINT_OUT | usb.TYPE_VENDOR | usb.RECIP_DEVICE

        # ... and use it to perform our core control request.
        return self.device.ctrl_transfer(type_data, number, value, index, data, timeout=timeout)


    def _populate_info_from_device(self):
        """ Populates this object with information about the target device, and its bootloader. """

        # Read the protocol version from the device descriptor.
        self.protocol = self.device.bcdDevice >> 8

        # Read the raw information packet, and parse it into its components.
        if self.protocol == 2:
            info_packet = self._request_in(self.REQUEST_GET_INFO, 6)
            self.flash_size, self.page_size, encoded_write_duration, self.signature = struct.unpack(">HBBH", info_packet)
        elif self.protocol == 1:
            info_packet = self._request_in(self.REQUEST_GET_INFO, 4)
            self.flash_size, self.page_size, encoded_write_duration = struct.unpack(">HBB", info_packet)
            self.signature = 0
        else:
            raise ValueError("Trying to handle a device with an unknown protocol!")


        # Compute the page count, for later convenience.
        self.page_count = int(self.flash_size / self.page_size)

        # Account for possible integer-division errors in page-count computation.
        if (self.page_count * self.page_size < self.flash_size):
            self.page_count += 1

        # Parse our encoded write duration: essentially, we strip out the MSB, which is a flag.
        self.write_duration_ms = encoded_write_duration & 0x7f

        # If we're not in "fast mode", delay for another 2ms per write, per the micronucleus spec.
        if not self.fast_mode:
            self.write_duration_ms += 2

        # Compute the total duration we'll want to wait to erase all pages.
        # We assume each page erasure takes the same amount of time as a write, on most platforms.
        self.erase_duration_ms = self.write_duration_ms * self.page_count

        # If that flag is set, our erase duration is a quarter of the time it'd take to write to every page.
        if (encoded_write_duration & 0x80):
            self.erase_duration_ms /= 4

        # Finally, figure out where our bootloader starts.
        # Note that this is roughly equivalent to self.flash_size, as the bootloader starts just after the
        # user program, but it
        self.bootloader_start = self.page_count * self.page_size


    def _print_target_info(self, print_function):
        """ Prints information about the relevant board, if possible."""

        print_function("    Micronucleus protocol supported: v{}".format(self.protocol))
        print_function("    Processor: {}".format(self.get_cpu_name()))
        print_function("    Maximum program size: {} B".format(self.flash_size))
        print_function("    Page size: {} B".format(self.page_size))
        print_function("    Page count: {}".format(self.page_count))
        print_function("    Sleep time between writes: {} ms".format(self.write_duration_ms))
        print_function("")


    def erase(self):
        """ Erases the board's program flash. """

        requires_reconnect = False

        # Ask the board to erase its flash...
        try:
            self._request_out(self.REQUEST_ERASE_FLASH)
        except usb.core.USBError:
            requires_reconnect = True

        # ... and wait for that to complete.
        time.sleep(self.erase_duration_ms / 1000.0)

        # If we error'd out, this is likely because the board got caught up erasing
        # and failed to handle its USB communication duties. Reconnect.
        if requires_reconnect:
            try:
                self.reconnect()
            except BoardNotFoundError:
                raise ProgrammingFailureError()


    def size_to_program(self, program_data):
        # We always program the entire flash, no matter the program size.
        return self.flash_size


    def program(self, program_data, status_callback=None):
        """ Programs a given binary program to the microcontroller's flash memory. """

        # Extract the user's reset address from the given program.
        reset_address = self._extract_reset_address(program_data)

        # Erase the device's flash.
        self.erase()

        # For each page in the given program...
        for page_address in range(0, self.flash_size, self.page_size):

            # Determine if this is the first/last page, to enable special page handling.
            is_first_page = (page_address == 0)
            is_last_page  = (page_address >= (self.bootloader_start - self.page_size))

            # Grab a copy of the page of data to program.
            try:
                data_to_program = bytearray(program_data[page_address : page_address + self.page_size])
            except IndexError:
                # If this is the last page, and we didn't have data, inject a page-size worth of filler bytes,
                # as we always need to program the last page in flash.
                if is_last_page:
                    data_to_program = bytearray()

                # Otherwise, continue. We can't abort early, as we'll still need to program the last page.
                else:
                    continue

            # If this is the first page, replace the reset vector with a jump to the bootloader.
            if is_first_page:
                self._patch_first_page(data_to_program)

            # If this is the last page, inject our user reset vector to be used by the bootloader.
            if is_last_page:
                self._patch_last_page(data_to_program, reset_address)

            # Finally, write the page to the device.
            if data_to_program:
                self.__raw_write_page(page_address, data_to_program)

            # Issue our status callback to indicate our progress.
            if callable(status_callback):
                status_callback(page_address, self.flash_size)


    def _extract_reset_address(self, program_data):
        """ Attempt to extract the reset address of the relevant program from the program data's first page. """

        # Split the start of the buffer into a pair of words, which should contain our relevant data.
        first_word, second_word = struct.unpack("<HH", program_data[0:4])

        # If the first word is a long jump, return its immediate argument directly.
        if first_word == self.AVR_LONG_JUMP_OPCODE:
            return second_word
        elif (first_word & self.AVR_RJMP_OPCODE_MASK) == self.AVR_RJMP_OPCODE:
            reset_address_words = (first_word & self.AVR_RJMP_OFFSET_MASK) + 1
            return reset_address_words * 2
        else:
            raise ValueError("First page does not seem to contain valid AVR code! Failing out!")


    def _patch_first_page(self, page_data):
        """ Patches a jump-to-bootloader into the first page of the user program. """


        if self.protocol == 2:
            self._patch_in_jump(page_data, 0, self.bootloader_start)


    def _patch_last_page(self, page_data, reset_address):
        """ Patches the user reset address into the last double-word of the user program.
            Used by the bootloader to identify the location of the relevant target.
        """

        # If our last page isn't sized to a full page, extend it to be so.
        # This is necessary to include the user reset vector so micronucleus knows how to start the user program.
        if len(page_data) < self.page_size:
            padding_size = self.page_size - len(page_data)
            padding = b'\xFF' * padding_size

            page_data.extend(padding)

        # The bootloader's final jump to the user program should always take up the DWORD _just before_ the bootloader.
        jump_instruction_address = self.bootloader_start - 4
        self._patch_in_jump(page_data, jump_instruction_address, reset_address)


    def _patch_in_jump(self, page_data, jump_instruction_address, jump_target):
        """ Patches a given data buffer to contain a jump instruction.

        Params:
            data_buffer -- The bytearray buffer to be modified.
            offset      -- The current offset in the bytearray buffer.
            jump_target -- The target of the relevant jump
        """

        # Compute how far into the current page we are.
        offset_into_page = jump_instruction_address % self.page_size

        # If we can reach the target using a relative jump, use one.
        if jump_target <= self.AVR_RJMP_REACH_BYTES:

            # Compute the AVR RJMP instruction.
            # First, we'll figure out the offset to the relevant value in bytes.
            offset_bytes = (jump_target - jump_instruction_address)
            offset_words = (int(offset_bytes / 2) - 1) & self.AVR_RJMP_OFFSET_MASK
            instruction  = self.AVR_RJMP_OPCODE | offset_words

            # ... and patch it into the relevant program.
            page_data[offset_into_page + 0] = instruction & 0xFF
            page_data[offset_into_page + 1] = instruction >> 8

        # Otherwise, use a long jump instruction.
        else:
           page_data[offset_into_page + 0] = self.AVR_LONG_JUMP_OPCODE & 0xff
           page_data[offset_into_page + 1] = self.AVR_LONG_JUMP_OPCODE >> 8
           page_data[offset_into_page + 2] = jump_target               & 0xff
           page_data[offset_into_page + 3] = jump_target               >> 8


    def __raw_write_page(self, address, data):
        """ Writes a page to the microcontroller's firmware. This should never be used directly!
            Instead, call program(), which handles reset vector redirection to ensure the bootloader
            runs correctly each time.
        """

        #
        if self.protocol == 1:
            self.__raw_write_page_v1(address, data)
        else:
            self.__raw_write_page_v2(address, data)




    def __raw_write_page_v2(self, address, data):
        """ Variant of raw_write_page for the micronucleus v2 protocol. """

        import sys

        # Extend out the data to always be page_size.
        if (len(data) < self.page_size):
            padding_size = self.page_size - len(data)
            data += b'\xFF' * padding_size

        # Send the address of the page we want to write...
        self._request_out(self.REQUEST_WRITE_PAGE, value=self.page_size, index=address)

        # ... and then send its contents.
        for offset in range(0, self.page_size, 4):

            # Grab the DWORD we're programming.
            chunk = data[offset : offset + 4]

            # Spread the data across index and value.
            # This is kind of icky, but it allows for a smaller bootloader.
            value_chunk = (chunk[1] << 8) | chunk[0]
            index_chunk = (chunk[3] << 8) | chunk[2]
            self._request_out(self.REQUEST_WRITE_DWORD, value=value_chunk, index=index_chunk)

        # Once we've sent a full page worth of data, wait for everything to complete.
        time.sleep(self.write_duration_ms / 1000.0)


    def __raw_write_page_v1(self, address, data):
        """ Writes a page to the microcontroller's firmware. This should never be used directly!
            Instead, call program(), which handles reset vector redirection to ensure the bootloader
            runs correctly each time.
        """

        import sys

        # Extend out the data to always be page_size.
        if (len(data) < self.page_size):
            padding_size = self.page_size - len(data)
            data += b'\xFF' * padding_size

        # Issue the write request...
        self._request_out(self.REQUEST_WRITE_PAGE, value=self.page_size, index=address, data=data)

        # ... and wait for it to complete.
        time.sleep(self.write_duration_ms / 1000.0)


    def get_cpu_name(self):
        """ Returns a short description of the relevant board's main processor. """

        if self.protocol == 1:
            return "cannot be detected (using the v1 protocol)"
        elif self.signature in self.AVR_NAMES:
            return self.AVR_NAMES[self.signature]
        else:
            return "unknown (signature: {})".format(hex(self.signature))


    def run_user_program(self):
        """ Requests that the currently-programmed user application be executed. """
        self._request_out(self.REQUEST_START_APPLICATION)





