"""Bound and freeze external XLSX bytes before openpyxl sees them."""
from contextlib import contextmanager
import hashlib
from pathlib import Path
import struct
from tempfile import SpooledTemporaryFile
from xml.etree.ElementTree import XMLParser, ParseError
from zipfile import ZipFile, BadZipFile, ZIP_STORED, ZIP_DEFLATED


MAX_INPUT = 32 * 1024 * 1024
MAX_MEMBER = 16 * 1024 * 1024
MAX_EXPANDED = 64 * 1024 * 1024
MAX_CENTRAL = 1024 * 1024
MAX_MEMBERS = 1024
MAX_RATIO = 1000
MAX_XML_NODES = 1_000_000
MAX_SHARED_STRINGS = 200_000
CHUNK = 64 * 1024


class WorkbookInputError(ValueError):
    pass


def _limit():
    raise WorkbookInputError('This workbook exceeds safe XLSX resource limits. Use a smaller crew workbook.')


class _XMLBudget:
    def __init__(self):
        self.nodes = self.strings = 0
        self.xml_parts = {'[Content_Types].xml'}
        self.xml_extensions = {'xml', 'rels', 'vml'}


class _XMLTarget:
    def __init__(self, budget, *, manifest=False):
        self.budget = budget;self.depth = 0;self.manifest = manifest

    def start(self, tag, attributes):
        self.depth += 1;self.budget.nodes += 1
        local = tag.rsplit('}', 1)[-1]
        if local == 'si':self.budget.strings += 1
        if self.depth > 64 or self.budget.nodes > MAX_XML_NODES or self.budget.strings > MAX_SHARED_STRINGS:
            _limit()
        if self.manifest and 'xml' in attributes.get('ContentType', '').lower():
            if local == 'Override':
                part = attributes.get('PartName', '')
                if not part.startswith('/') or part.startswith('//'):
                    raise WorkbookInputError('The workbook has an invalid XML part reference.')
                self.budget.xml_parts.add(part[1:])
            elif local == 'Default':self.budget.xml_extensions.add(attributes.get('Extension', '').lower())

    def end(self, tag):self.depth -= 1
    def data(self, data):pass
    def close(self):pass
    def doctype(self, *args):
        raise WorkbookInputError('DTD and entity declarations are not supported in crew workbooks.')


def _directory_budget(stream, size):
    # Bound the central directory BEFORE ZipFile allocates its member objects.
    stream.seek(max(0, size - 65557));tail = stream.read(65557)
    index = tail.rfind(b'PK\x05\x06')
    if index < 0 or index + 22 > len(tail):raise BadZipFile('Missing ZIP end record')
    _, disk, directory_disk, count_disk, count, central, offset, comment = struct.unpack_from('<4s4H2LH', tail, index)
    if index + 22 + comment != len(tail) or disk or directory_disk or count_disk != count:
        raise WorkbookInputError('Choose a standard single-file XLSX workbook.')
    if count > MAX_MEMBERS or central > MAX_CENTRAL:_limit()
    if offset + central > size - len(tail) + index:raise BadZipFile('Invalid central directory')
    stream.seek(0)


def _preflight(stream, size):
    _directory_budget(stream, size)
    budget = _XMLBudget();total = 0
    with ZipFile(stream) as archive:
        members = archive.infolist()
        if len(members) > MAX_MEMBERS:_limit()
        names = set()
        for member in members:
            if member.filename in names:raise WorkbookInputError('Duplicate XLSX package parts are not supported.')
            names.add(member.filename)
            if member.flag_bits & 1 or member.compress_type not in (ZIP_STORED, ZIP_DEFLATED):
                raise WorkbookInputError('Encrypted or unsupported XLSX compression is not supported.')
            if member.file_size > MAX_MEMBER or member.compress_size > MAX_INPUT:_limit()
        if '[Content_Types].xml' not in names:raise BadZipFile('Missing workbook content types')
        # Read content types first: XML parts can have arbitrary extensions.
        ordered = [archive.getinfo('[Content_Types].xml')] + [m for m in members if m.filename != '[Content_Types].xml']
        for member in ordered:
            xml = (member.filename in budget.xml_parts or member.filename.rsplit('.', 1)[-1].lower() in budget.xml_extensions)
            parser = XMLParser(target=_XMLTarget(budget, manifest=member.filename == '[Content_Types].xml')) if xml else None
            expanded = 0
            with archive.open(member) as source:
                while True:
                    block = source.read(CHUNK)
                    if not block:break
                    expanded += len(block);total += len(block)
                    if (expanded > MAX_MEMBER or total > MAX_EXPANDED
                        or expanded > max(member.compress_size, 1) * MAX_RATIO):_limit()
                    if parser is not None:parser.feed(block)
            if expanded != member.file_size:raise BadZipFile('Inconsistent expanded size')
            if parser is not None:parser.close()
    stream.seek(0)


@contextmanager
def workbook_snapshot(path):
    path = Path(path)
    if path.suffix.casefold() != '.xlsx':raise WorkbookInputError('Choose an Excel workbook (.xlsx).')
    try:
        with SpooledTemporaryFile(max_size=4 * 1024 * 1024, mode='w+b') as frozen:
            digest = hashlib.sha256();size = 0
            with path.open('rb') as original:
                while True:
                    block = original.read(CHUNK)
                    if not block:break
                    size += len(block)
                    if size > MAX_INPUT:_limit()
                    digest.update(block);frozen.write(block)
            _preflight(frozen, size)
            yield frozen, digest.hexdigest()
    except (BadZipFile, ParseError, EOFError, NotImplementedError) as exc:
        raise WorkbookInputError('Choose a valid, unencrypted XLSX workbook.') from exc
