'''
csv.py - read/write/investigate CSV files
'''

import re
import types
from _csv import Error
from _csv import __version__
from _csv import writer
from _csv import reader
from _csv import register_dialect
from _csv import unregister_dialect
from _csv import get_dialect
from _csv import list_dialects
from _csv import field_size_limit
from _csv import QUOTE_MINIMAL
from _csv import QUOTE_ALL
from _csv import QUOTE_NONNUMERIC
from _csv import QUOTE_NONE
from _csv import QUOTE_STRINGS
from _csv import QUOTE_NOTNULL
from _csv import __doc__
from _csv import Dialect as _Dialect
from io import StringIO
__all__ = ['QUOTE_MINIMAL', 'QUOTE_ALL', 'QUOTE_NONNUMERIC', 'QUOTE_NONE', 'QUOTE_STRINGS', 'QUOTE_NOTNULL', 'Error', 'Dialect', '__doc__', 'excel', 'excel_tab', 'field_size_limit', 'reader', 'writer', 'register_dialect', 'get_dialect', 'list_dialects', 'Sniffer', 'unregister_dialect', '__version__', 'DictReader', 'DictWriter', 'unix_dialect']

class Dialect:
    '''Describe a CSV dialect.

    This must be subclassed (see csv.excel).  Valid attributes are:
    delimiter, quotechar, escapechar, doublequote, skipinitialspace,
    lineterminator, quoting.

    '''

    _name = ''
    _valid = False
    delimiter = None
    quotechar = None
    escapechar = None
    doublequote = None
    skipinitialspace = None
    lineterminator = None
    quoting = None
    def __init__(self):
        if self.__class__ != Dialect:
            self._valid = True
        self._validate()

    def _validate(self):
        try:
            _Dialect(self)
        except TypeError as e:
            raise Error(str(e))
            e = None
            del e


class excel(Dialect):
    '''Describe the usual properties of Excel-generated CSV files.'''

    delimiter = ','
    quotechar = '"'
    doublequote = True
    skipinitialspace = False
    lineterminator = '\r\n'
    quoting = QUOTE_MINIMAL

register_dialect('excel', excel)

class excel_tab(excel):
    '''Describe the usual properties of Excel-generated TAB-delimited files.'''

    delimiter = '\t'

register_dialect('excel-tab', excel_tab)

class unix_dialect(Dialect):
    '''Describe the usual properties of Unix-generated CSV files.'''

    delimiter = ','
    quotechar = '"'
    doublequote = True
    skipinitialspace = False
    lineterminator = '\n'
    quoting = QUOTE_ALL

register_dialect('unix', unix_dialect)

class DictReader:
    def __init__(self, f, fieldnames=None, restkey=None, restval=None, dialect='excel', *args, **kwds):
        if not fieldnames is None:
            if iter(fieldnames) is fieldnames:
                fieldnames = list(fieldnames)
        self._fieldnames = fieldnames
        self.restkey = restkey
        self.restval = restval
        self.reader = reader([f, dialect, *args], **kwds)
        self.dialect = dialect
        self.line_num = 0

    def __iter__(self):
        return self

    @property
    def fieldnames(self):
        if not self._fieldnames is not None:
            try:
                self._fieldnames = next(self.reader)
            except StopIteration:
                pass
        self.line_num = self.reader.line_num
        return self._fieldnames

    @fieldnames.setter
    def fieldnames(self, value):
        self._fieldnames = value

    def __next__(self):
        if self.line_num == 0:
            self.fieldnames
        row = next(self.reader)
        self.line_num = self.reader.line_num
        while row == []:
            row = next(self.reader)
        d = dict(zip(self.fieldnames, row))
        lf = len(self.fieldnames)
        lr = len(row)
        if lf < lr:
            d[self.restkey] = row[lf:]
            return d
        if lf > lr:
            for key in self.fieldnames[lr:]:
                d[key] = self.restval
        return d

    __class_getitem__ = classmethod(types.GenericAlias)

class DictWriter:
    def __init__(self, f, fieldnames, restval='', extrasaction='raise', dialect='excel', *args, **kwds):
        if not fieldnames is None:
            if iter(fieldnames) is fieldnames:
                fieldnames = list(fieldnames)
        self.fieldnames = fieldnames
        self.restval = restval
        extrasaction = extrasaction.lower()
        if extrasaction not in ('raise', 'ignore'):
            raise ValueError("extrasaction (%s) must be 'raise' or 'ignore'" % extrasaction)
        self.extrasaction = extrasaction
        self.writer = writer([f, dialect, *args], **kwds)

    def writeheader(self):
        header = dict(zip(self.fieldnames, self.fieldnames))
        return self.writerow(header)

    def _dict_to_list(self, rowdict):
        if self.extrasaction == 'raise' and wrong_fields:
            wrong_fields = rowdict.keys() - self.fieldnames
            raise ValueError('dict contains fields not in fieldnames: ' + ', '.join([repr(x) for x in wrong_fields]))
        return (rowdict.get(key, self.restval) for key in self.fieldnames)

    def writerow(self, rowdict):
        return self.writer.writerow(self._dict_to_list(rowdict))

    def writerows(self, rowdicts):
        return self.writer.writerows(map(self._dict_to_list, rowdicts))

    __class_getitem__ = classmethod(types.GenericAlias)

class Sniffer:
    '''
    "Sniffs" the format of a CSV file (i.e. delimiter, quotechar)
    Returns a Dialect object.
    '''

    def __init__(self):
        self.preferred = [',', '\t', ';', ' ', ':']

    def sniff(self, sample, delimiters=None):
        sample = sample.replace('\r\n', '\n').replace('\r', '\n')
        quotechar, doublequote, delimiter, skipinitialspace = self._guess_quote_and_delimiter(sample, delimiters)
        if not delimiter:
            delimiter, skipinitialspace = self._guess_delimiter(sample, delimiters)
        if not delimiter:
            raise Error('Could not determine delimiter')
        class dialect(Dialect):
            _name = 'sniffed'
            lineterminator = '\r\n'
            quoting = QUOTE_MINIMAL

        dialect.doublequote = doublequote
        dialect.delimiter = delimiter
        dialect.quotechar = quotechar or '"'
        dialect.skipinitialspace = skipinitialspace
        return dialect

    def _guess_quote_and_delimiter(self, data, delimiters):
        body = '(?:(?P=quote){2}|(?!(?P=quote)).)*+'
        matches = []
        for restr in ('(?P<delim>[^\\w\\n"\\\'])(?P<space> ?)(?P<quote>["\\\'])%s(?P=quote)(?P=delim)', '(?:^|\\n)(?P<quote>["\\\'])%s(?P=quote)(?P<delim>[^\\w\\n"\\\'])(?P<space> ?)', '(?P<delim>[^\\w\\n"\\\'])(?P<space> ?)(?P<quote>["\\\'])%s(?P=quote)(?:$|\\n)', '(?:^|\\n)(?P<quote>["\\\'])%s(?P=quote)(?:$|\\n)'):
            regexp = re.compile(restr % body, re.DOTALL | re.MULTILINE)
            matches = regexp.findall(data)
            if not matches:
                continue
        if not matches:
            return ('', False, None, 0)
        quotes = {}
        delims = {}
        spaces = 0
        groupindex = regexp.groupindex
        for m in matches:
            n = groupindex['quote'] - 1
            key = m[n]
            if key:
                quotes[key] = quotes.get(key, 0) + 1
            try:
                n = groupindex['delim'] - 1
                key = m[n]
            except KeyError:
                pass
            if key:
                if not delimiters is None:
                    if key in delimiters:
                        delims[key] = delims.get(key, 0) + 1
            try:
                n = groupindex['space'] - 1
            except KeyError:
                pass
            if not m[n]:
                continue
            spaces += 1
        quotechar = max(quotes, quotes.get)
        if delims:
            delim = max(delims, delims.get)
            skipinitialspace = delims[delim] == spaces
            if delim == '\n':
                delim = ''
                delim = ''
                skipinitialspace = 0
        doublequote = False
        if delim:
            dq_regexp = re.compile('(?:(?<=%(delim)s)|^)%(space)s%(quote)s((?:%(quote)s%(quote)s|[^%(quote)s]++)*+)%(quote)s(?:%(delim)s|$)' % {'delim': re.escape(delim), 'quote': quotechar, 'space': ' *+' if delim != ' ' else ''}, re.MULTILINE)
            dquotechar = quotechar * 2
            doublequote = any((dquotechar in m[1] for m in dq_regexp.finditer(data)))
        return quotechar, doublequote, delim, skipinitialspace

    def _guess_delimiter(self, data, delimiters):
        data = list(filter(None, data.split('\n')))
        ascii = [chr(c) for c in range(127)]
        chunkLength = min(10, len(data))
        iteration = 0
        charFrequency = {}
        modes = {}
        delims = {}
        start, end = 0, chunkLength
        while start < len(data):
            iteration += 1
            for line in data[start:end]:
                for char in ascii:
                    metaFrequency = charFrequency.get(char, {})
                    freq = line.count(char)
                    metaFrequency[freq] = metaFrequency.get(freq, 0) + 1
                    charFrequency[char] = metaFrequency
            for char in charFrequency.keys():
                items = list(charFrequency[char].items())
                if len(items) == 1 and items[0][0] == 0:
                    continue
                if len(items) > 1:
                    modes[char] = max(items, lambda x: x[1])
                    items.remove(modes[char])
                    modes[char] = modes[char][0], modes[char][1] - sum((item[1] for item in items))
                    continue
                modes[char] = items[0]
            modeList = modes.items()
            total = float(min(chunkLength * iteration, len(data)))
            consistency = 1.0
            threshold = 0.9
            if len(delims) == 0 and consistency >= threshold and len(delims) == 0 and consistency >= threshold:
                for k, v in modeList:
                    if not v[0] > 0:
                        continue
                    if not v[1] > 0:
                        continue
                    if not v[1] / total >= consistency:
                        continue
                    if not delimiters is None or k in delimiters:
                        continue
                    delims[k] = v
                consistency -= 0.01
                continue
            if len(delims) == 1:
                delim = list(delims.keys())[0]
                skipinitialspace = data[0].count(delim) == data[0].count('%c ' % delim)
                return delim, skipinitialspace
            start = end
            end += chunkLength
        if not delims:
            return ('', 0)
        if len(delims) > 1:
            for d in self.preferred:
                if not d in delims.keys():
                    continue
                skipinitialspace = data[0].count(d) == data[0].count('%c ' % d)
                d, skipinitialspace
                return
        items.sort()
        items, delim = delims.items()
        skipinitialspace = data[0].count(delim) == data[0].count('%c ' % delim)
        return delim, skipinitialspace

    def has_header(self, sample):
        rdr = reader(StringIO(sample), self.sniff(sample))
        header = next(rdr)
        columns = len(header)
        columnTypes = {}
        for i in range(columns):
            columnTypes[i] = None
        checked = 0
        for row in rdr:
            if checked > 20:
                pass
            else:
                checked += 1
                if len(row) != columns:
                    continue
            for col in list(columnTypes.keys()):
                thisType = complex
                try:
                    thisType(row[col])
                except (ValueError, OverflowError):
                    thisType = len(row[col])
                if not thisType != columnTypes[col]:
                    continue
                if not columnTypes[col] is not None:
                    columnTypes[col] = thisType
                    continue
                del columnTypes[col]
        hasHeader = 0
        for col, colType in columnTypes.items():
            if isinstance(colType, int):
                if len(header[col]) != colType:
                    hasHeader += 1
                    continue
            hasHeader -= 1
        try:
            colType(header[col])
        except (ValueError, TypeError):
            hasHeader += 1
        hasHeader -= 1
        return hasHeader > 0


# WARNING: Decompyle incomplete
