import re
__all__ = ['NoSectionError', 'DuplicateSectionError', 'NoOptionError', 'InterpolationError', 'InterpolationDepthError', 'InterpolationSyntaxError', 'ParsingError', 'MissingSectionHeaderError', 'ConfigParser', 'SafeConfigParser', 'RawConfigParser', 'DEFAULTSECT', 'MAX_INTERPOLATION_DEPTH']
DEFAULTSECT = 'DEFAULT'
MAX_INTERPOLATION_DEPTH = 10

class Error(Exception):
    pass

class NoSectionError(Error):
    pass

class DuplicateSectionError(Error):
    pass

class NoOptionError(Error):
    pass

class InterpolationError(Error):
    pass

class InterpolationMissingOptionError(InterpolationError):
    pass

class InterpolationSyntaxError(InterpolationError):
    pass

class InterpolationDepthError(InterpolationError):
    pass

class ParsingError(Error):
    pass

class MissingSectionHeaderError(ParsingError):
    pass

class RawConfigParser:
    pass

import UserDict as _UserDict

class _Chainmap(_UserDict.DictMixin):
    pass

class ConfigParser(RawConfigParser):
    pass

class SafeConfigParser(ConfigParser):
    pass

# WARNING: Decompyle incomplete
