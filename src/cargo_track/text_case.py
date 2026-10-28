"""Deterministic, offline casing rules. No identity or route inference."""
from __future__ import annotations

import re

RULE_VERSION = 1
ACRONYMS = {w.casefold(): w for w in (
    'HSE', 'QC', 'QA', 'NAV', 'IT', 'HR', 'DPO', 'ETO', 'AB', 'OS',
    'ROV', 'DP', 'GPS', 'VHF', 'UHF', 'HF', 'PPE', 'PVC', 'CPVC', 'HDPE',
    'LED', 'USB', 'UPS', 'AC', 'DC', 'HVAC', 'CCTV', 'SCBA', 'CO2', 'SS',
    'MGO', 'MDO', 'LSA', 'FFA', 'OEM', 'PLC', 'AIS', 'EPIRB', 'SART', 'NDT',
    'OIM', 'HLO', 'HDA', 'QAQC', 'FRC', 'FSO', 'FPSO', 'CNC', 'API', 'IMO',
    'SOLAS', 'MARPOL', 'ECDIS', 'GMDSS', 'STCW', 'ADCP', 'CTD', 'DGPS', 'OBS')}
# Ambiguous units (mA / MA, mW / MW) are deliberately case sensitive.
UNITS = {w: w for w in ('kg', 'g', 'mg', 'mm', 'cm', 'm', 'km', 'ml', 'mL', 'L',
    'kW', 'MW', 'mW', 'W', 'V', 'kV', 'A', 'mA', 'MA', 'Ah', 'mAh', 'Hz', 'kHz', 'MHz', 'GHz', 'bar', 'psi', 'Pa', 'kPa', 'MPa', 'Nm', 'N', 'kN', 'kWh')}
UNIT_ALIASES = {'KG': 'kg', 'MM': 'mm', 'CM': 'cm', 'KW': 'kW', 'HZ': 'Hz', 'KGS': 'kg', 'ML':'mL', 'KV':'kV', 'KWH':'kWh'}
EXCEPTIONS = {'mcdonald': 'McDonald', 'mcdonnell': 'McDonnell', 'mckenzie': 'McKenzie',
              'iphone': 'iPhone', 'ipad': 'iPad', 'ebay': 'eBay'}
TOKEN = re.compile(r"[^\W_\u3400-\u9fff\uf900-\ufaff]+(?:['’][^\W_\u3400-\u9fff\uf900-\ufaff]+)*", re.UNICODE)
ORDINARY_CARGO = set(('safety helmet pipe pump hose box crate cable drum rope tank bolt nut washer valve filter '
    'oil fuel air water fresh drinking spare parts equipment material materials antenna battery charger '
    'life jacket glove gloves shoe shoes boot boots fire extinguisher tool tools set kit bottle cylinder '
    'steel stainless plastic rubber portable electric hydraulic motor generator compressor connector '
    'laptop computer monitor printer radio radar beacon light lamp tube pallet bag carton package '
    'medical oxygen food supply supplies diesel engine bearing chain shackle sling hook sensor').split())


def normalize(value, kind='cargo'):
    """Return (text, review notes); retain line structure for cargo descriptions."""
    value = str(value) if value is not None else ''
    if kind == 'cargo':
        value = '\n'.join(re.sub(r'[^\S\n]+', ' ', line).strip() for line in value.replace('\r\n', '\n').replace('\r', '\n').split('\n')).strip()
    else:
        value = re.sub(r'\s+', ' ', value).strip()
    notes = set()
    if value.startswith('='):
        return value, ['Formula-like text; verify the intended description']

    def word(match):
        token = match.group()
        if not any(c.isascii() and c.isalpha() for c in token):
            return token
        folded = token.casefold()
        if kind != 'name' and folded in ACRONYMS:
            return ACRONYMS[folded]
        if kind == 'cargo':
            if token in UNITS:
                return UNITS[token]
            if token in UNIT_ALIASES:
                return UNIT_ALIASES[token]
            if any(c.isdigit() for c in token):
                # Preserve numbers, dimensions and model identifiers verbatim.
                return token
            if token.isascii() and token.isalpha() and token.isupper() and len(token)<=4 and folded not in ORDINARY_CARGO:
                notes.add('Check abbreviation spelling')
                return token
            if folded not in ORDINARY_CARGO and re.fullmatch(r'[A-Za-z]{1,4}', token) and (
                    (match.start() and value[match.start()-1] in '-_/') or
                    (match.end() < len(value) and value[match.end()] in '-_/')):
                notes.add('Check model / code spelling')
                return token
        if folded in EXCEPTIONS:
            return EXCEPTIONS[folded]
        if kind == 'name' and re.fullmatch(r'[A-Za-z]', token):
            return token.upper()
        # Correctly written internal capitals may be a brand or personal spelling.
        if token[0].islower() and any(c.isupper() for c in token[1:]) or (
                token[0].isupper() and any(c.isupper() for c in token[1:]) and any(c.islower() for c in token[1:])):
            if kind == 'cargo' and folded not in ORDINARY_CARGO:
                notes.add('Check mixed-case brand / code')
                return token
            if re.fullmatch(r'(?:Mc|Mac)[A-Z][a-z]+', token):
                return token
        return token.title()

    return TOKEN.sub(word, value), sorted(notes)


def personnel_record(record, preserve=None):
    """Store source and confirmed spelling per field; repeated calls are stable."""
    result = dict(record)
    previous = record.get('text_case', {})
    metadata = {}
    for field in ('name', 'position'):
        raw = str(record[field]) if record.get(field) is not None else ''
        info = previous.get(field, {})
        keep = preserve if preserve is not None else record.get('preserve_text_case', False)
        if info.get('value') == raw and (preserve is None or info.get('preserve') == keep):
            metadata[field] = dict(info)
            continue
        value, notes = (raw.strip(), []) if keep else normalize(raw, field)
        result[field] = value
        metadata[field] = {'raw': raw, 'value': value, 'preserve': bool(keep),
                           'version': RULE_VERSION, 'review': notes}
    result['text_case'] = metadata
    if preserve is not None:
        result['preserve_text_case'] = bool(preserve)
    return result


def legacy_personnel(record):
    """Recover only proven old .title() conversions, respecting later edits."""
    result = dict(record)
    originals = record.get('original_values', {})
    for field in ('name', 'position'):
        if field in record.get('text_case', {}):
            continue
        current = str(record.get(field, ''))
        source = str(originals.get(field, current))
        if current == source.strip() or current == source.strip().title():
            result[field] = source
        else:
            result.setdefault('text_case', {})
            result['text_case'] = dict(result['text_case'])
            result['text_case'][field] = {'raw': current, 'value': current, 'preserve': True,
                                         'version': RULE_VERSION, 'review': []}
    return personnel_record(result)
