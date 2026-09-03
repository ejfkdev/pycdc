"""Generic MIME writer.

This module defines the class MimeWriter.  The MimeWriter class implements
a basic formatter for creating MIME multi-part files.  It doesn't seek around
the output file nor does it use large amounts of buffer space. You must write
the parts out in the order that they should occur in the final file.
MimeWriter does buffer the headers you add, allowing you to rearrange their
order.

"""

import mimetools
__all__ = ['MimeWriter']
import warnings
warnings.warn('the MimeWriter module is deprecated; use the email package instead', DeprecationWarning, 2)

class MimeWriter(()):
    pass

if __name__ == '__main__':
    import test.test_MimeWriter
