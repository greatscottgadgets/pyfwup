"""
Core definitions for pyfwup.
"""

class FwupTarget(object):
    """
    Abstract base class for pyfwup supported boards. Allows use in fwup-util and derivatives.
    """

    @classmethod
    def __search_descendent_classes(cls, condition):
        """
        Search all descendent classes for a class that meets the given condition.
        """

        # Search each of our subclasses for a class that matches the given condition.
        for subclass in cls.__subclasses__():

            # If we find a match, return it...
            if condition(subclass):
                return subclass

            # ... and allow each of its subclasses to do the same.
            match = subclass.__search_descendent_classes(condition)
            if match:
                return match

        # If we didn't find anything, return None.
        return None


    @classmethod
    def from_utility_name(cls, utility_name):
        """
        Returns the board type appropriate for the given utility name.
        """
        return cls.__search_descendent_classes(lambda subclass : subclass.FWUP_UTILITY_NAME == utility_name)


    @classmethod
    def from_target_name(cls, target_name):
        """
        Returns the board type appropriate for the given utility name.
        """
        return cls.__search_descendent_classes(lambda subclass : subclass.FWUP_TARGET_NAME == target_name)


    @staticmethod
    def _print_preconnect_info(print_function):
        """
        Prints any information that should be printed before a target object is connected.
        Useful for cases where target waits for e.g. a button press.

        This version should be overridden by the subclasses, where possible.
        It's guaranteed to have a print_function that's callable.
        """
        pass


    @classmethod
    def print_preconnect_info(cls, print_function=None):
        """
        Prints any information that should be printed before a target object is connected.
        Useful for cases where target waits for e.g. a button press.

        This version should be overridden by the subclasses, where possible.
        It's guaranteed to have a print_function that's callable.
        """

        if not print_function:
            print_function = print

        cls._print_preconnect_info(print_function)


    def _print_target_info(self, print_function):
        """
        Prints information about the relevant target, if possible.

        This version should be overridden by the subclasses, where possible.
        It's guaranteed to have a print_function that's callable.
        """
        pass


    def print_target_info(self, print_function=None):
        """
        Prints information about the relevant target, if possible.

        Base classes should prefer to override _print_board_info, as it will
        always be passed a callable print_function.
        """

        if not print_function:
            print_function = print

        self._print_target_info(print_function)


    def size_to_program(self, program_data):
        """
        Returns the size to program for a given binary.
        This function allows subclasses to override the size to be programmed, in case
        it needs to e.g. always program full pages, or always program the whole flash.
        """

        # By default, program exactly as much data as provided.
        return len(program_data)
