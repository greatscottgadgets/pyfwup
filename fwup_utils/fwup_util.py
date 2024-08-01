#!/usr/bin/env python
#
# Multi-firmware programming binary.
#

import os
import sys
import argparse
import platform
import usb, usb.backend.libusb1

from tqdm import tqdm

from fwup.core import FwupTarget
from fwup.errors import BoardNotFoundError

# TODO: automatically detect these?
from fwup.dfu import DFUTarget
from fwup.lpc43xx import LPC43xxTarget
from fwup.micronucleus import MicronucleusBoard
from fwup.fx3 import FX3Target

def log_stderr(string):
    """ Helper to log to stderr. """
    print(string, file=sys.stderr)

def log_null(string):
    """ Helper that discards input. """
    pass

def main():
    """ Simple programmer for pyfwup supported boards. """

    # Try to identify the type of board for the given utility based on the name it was called by.
    # This allows derivative programmers (e.g. microprog) to have unique binary names that implicitly
    # specify their target type.
    utility_name = os.path.basename(sys.argv[0])
    target_type = FwupTarget.from_utility_name(utility_name)

    # Figure out the name for our board type based on the binary name.
    target_name = target_type.FWUP_TARGET_NAME if target_type else "pyfwup"

    # Generate a simple argument parser.
    parser = argparse.ArgumentParser(description="Simple, python-based programmer for {} boards.".format(target_name))
    parser.add_argument('filename', metavar='bin_file', help='The file to be programmed.', nargs='?')
    parser.add_argument('--verbose', '-v', action='store_true', help='Provide to generate more detailed console output.')
    parser.add_argument('--quiet', '-q', action='store_true', help='Provide to disable console output during normal operation.')
    parser.add_argument('--no-run', action='store_true', dest='skip_run', help='Set to avoid running the program after upload.')
    parser.add_argument('--run-only', action='store_true', dest='run_only', help='If provided, runs the user application without uploading anything.')
    parser.add_argument('--erase-only', '-E', action='store_true', dest='erase_only', help='Erases the microcontroller without re-uploading a new program.')
    parser.add_argument('--info', '-I', action='store_true', dest='info_only', help="Reads only the board's identification information, and then exits.")
    parser.add_argument('--device', '-d', metavar='<vid>:<pid>', dest='device', help='Specify Vendor/Product ID of target device.')

    if target_type is None:
        parser.add_argument('--target', '-t', help="The type of target to be programmed.", default="dfu")

    args = parser.parse_args()
    run_programming = not args.erase_only and not args.run_only and not args.info_only

    # If we don't have a target name, search for one.:
    if target_type is None:
        try:
            target_type = FwupTarget.from_target_name(args.target)
        except AttributeError:
            pass

    # If our arguments are invalid, abort.
    if not (args.filename or args.erase_only or args.run_only or args.info_only):
        parser.print_help()
        sys.exit(-1)

    # If we couldn't figure out a target type, abort.
    if not target_type:
        log_stderr("Couldn't figure out which type of target to program. Did you supply a valid --target?")
        sys.exit(-2)

    # Handle various verbosity settings.
    log_verbose = log_stderr if (args.verbose or args.info_only) else log_null
    log_status  = log_null if args.quiet else log_stderr

    # Update the target name, in case we just searched for one.
    target_name = target_type.FWUP_TARGET_NAME

    # Read the binary data for the relevant file into memory.
    if run_programming:
        with open(args.filename, 'rb') as f:
            program_data = f.read()

    # Print preconnect info, if we have any.
    target_type.print_preconnect_info(log_status)

    # Extract VID/PID from the device argument
    device = {}
    if args.device:
        try:
            vid, pid = args.device.split(':')
            device['idVendor']  = int(vid, 16)
            device['idProduct'] = int(pid, 16)
        except ValueError:
            log_stderr("Cannot parse the device argument. Please supply a valid vid:pid pair.")
            sys.exit(-4)

    # On Windows we need to specify the libusb library location to create a backend.
    if platform.system() == "Windows":
        # Determine the path to libusb-1.0.dll.
        try:
            from importlib_resources import files # <= 3.8
        except:
            from importlib.resources import files # >= 3.9
        libusb_dll = os.path.join(files("usb1"), "libusb-1.0.dll")

        # Create a backend by explicitly passing the path to libusb_dll.
        backend = usb.backend.libusb1.get_backend(find_library=lambda x: libusb_dll)
    else:
        # On other systems we can just use the default backend.
        backend = usb.backend.libusb1.get_backend()

    # Figure out which to create based on the binary name.
    try:
        board = target_type(**device)
    except BoardNotFoundError:
        log_stderr("Could not find a {} board!".format(target_name))
        sys.exit(-3)

    # Print information about the connected board.
    log_status("")
    log_status("Target found!")
    board.print_target_info(log_verbose)

    if args.info_only:
        sys.exit(0)

    # Finally, program the relevant board...
    if run_programming:
        size_to_program = board.size_to_program(program_data)

        log_status("Programming {} bytes...".format(len(program_data)))
        with tqdm(total=size_to_program, ncols=80, unit='B', leave=False, disable=args.quiet) as progress:
            board.program(program_data, status_callback = lambda written, _ : progress.update(written))
        log_status("Programming complete!")

    # If we're in erase-only mode, erase.
    if args.erase_only:
        log_status("Erasing board...")
        board.erase()

    # ... and execute the user application.
    if args.run_only or (run_programming and not args.skip_run):
        log_status("\nRunning newly-programmed application.")
        board.run_user_program()

    log_status("")


# Allow this script to run by itself.
if __name__ == "__main__":
    main()
