#
# Generic error collection for pynucleus.
# This file is part of pynucleus.
#


class BoardNotFoundError(IOError):
	""" Class representing a condition where no board was found. """


class ProgrammingFailureError(IOError):
	""" Class representing a condition where programming failed. """
