#!/usr/bin/env python
#
# Micronucleus programmer (in python!)
#

from __future__ import print_function

import sys
import argparse

from tqdm import tqdm

from fwup.micronucleus import MicronucleusBoard


def log_stderr(string):
    """ Helper to log to stderr. """
    print(string, file=sys.stderr)

def log_null(string):
    """ Helper that discards input. """
    pass

def main():
    """
    Simple programmer for Micronucleus bootloaders -- but in python for easy distribution.
    """

    # Generate a simple argument parser.
    parser = argparse.ArgumentParser(description="Simple, python-based programmer for micronucleus boards.")
    parser.add_argument('filename', metavar='bin_file', help='The file to be programmed.', nargs='?')
    parser.add_argument('--verbose', '-v', action='store_true', help='Provide to generate more detailed console output.')
    parser.add_argument('--quiet', '-q', action='store_true', help='Provide to disable console output during normal operation.')
    parser.add_argument('--no-run', action='store_true', dest='skip_run', help='Set to avoid running the program after upload.')
    parser.add_argument('--run-only', action='store_true', dest='run_only', help='If provided, runs the user application without uploading anything.')
    parser.add_argument('--erase-only', '-E', action='store_true', dest='erase_only', help='Erases the microcontroller without re-uploading a new program.')
    parser.add_argument('--info', '-I', action='store_true', dest='info_only', help="Reads only the board's identification information, and then exits.")

    args = parser.parse_args()
    run_programming = not args.erase_only and not args.run_only and not args.info_only

    # If our arguments are invalid, abort.
    if not (args.filename or args.erase_only or args.run_only or args.info_only):
        parser.print_help()
        sys.exit(-1)

    # Handle various verbosity settings.
    log_verbose = log_stderr if (args.verbose or args.info_only) else log_null
    log_status  = log_null if args.quiet else log_stderr

    # Read the binary data for the relevant file into memory.
    if run_programming:
        with open(args.filename, 'rb') as f:
            program_data = f.read()

    # Ask the user to put the device into bootloader mode.
    log_status("Plug the target board in now.")
    log_status("If the board is already plugged in, you may need to unplug and replug it before it will be found.")

    # Attempt to connect to the relevant board.
    board = MicronucleusBoard()

    # Print out information about the board, assuming we were able to find one.
    log_status("")
    log_status("Board found!")
    log_verbose("    Micronucleus protocol supported: v{}".format(board.protocol))
    log_verbose("    Processor: {}".format(board.get_cpu_name()))
    log_verbose("    Maximum program size: {} B".format(board.flash_size))
    log_verbose("    Page size: {} B".format(board.page_size))
    log_verbose("    Page count: {}".format(board.page_count))
    log_verbose("    Sleep time between writes: {} ms".format(board.write_duration_ms))
    log_verbose("")

    if args.info_only:
        sys.exit(0)


    # Finally, program the relevant board...
    if run_programming:
        log_status("Programming {} bytes...".format(len(program_data)))
        with tqdm(total=board.flash_size, ncols=80, unit='B', leave=False, disable=args.quiet) as progress:
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
