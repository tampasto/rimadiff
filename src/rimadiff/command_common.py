import re
import shutil
from pathlib import Path

import click


COMMON_EPILOG="""
    \b
    Environment variables:
      RIMADIFF_CONFIG_DIR    Default value for --config-dir
      RIMADIFF_HISTORY_PATH  Default value for --history-path
    """

config_dir_option = click.option(
    '--config-dir',
    metavar='PATH', envvar='RIMADIFF_CONFIG_DIR',
    type=click.Path(
        file_okay=False, writable=True, resolve_path=True, path_type=Path),
    help='Path to the configuration directory'
    )

history_path_option = click.option(
    '--history-path',
    metavar='PATH', envvar='RIMADIFF_HISTORY_PATH',
    type=click.Path(
        dir_okay=False, writable=True, resolve_path=True, path_type=Path),
    help='Path to the history database file'
    )


def determine_file_type(src, format_):
    name_dict = {
        ext[1:]: name
        for name, exts, _ in shutil.get_unpack_formats()
        for ext in exts
        }
    name_dict['json'] = 'json'
    valid_formats = sorted(name_dict, key=lambda e: (e != 'json', e))

    if src.is_dir():
        type_ = 'dir'
    elif format_:
        type_ = name_dict.get(format_)
    else:
        filename = src.name.lower()
        type_ = None
        for ext, name_type in name_dict.items():
            if filename.endswith(f'.{ext}'):
                type_ = name_type
                break
    return type_, valid_formats


def get_date_formats(format_strings, quit_error):
    ph_simple = 'YmdHMS'
    date_formats = []
    for fmt in format_strings:
        err_common = (
            f' in general configuration file import_date_formats value {fmt!r}'
            )

        n = 0
        while (pos := fmt.find('%', n)) != -1:
            char = (fmt[pos+1] if pos+1 < len(fmt) else '%')
            if char not in f'{ph_simple}z':
                ph = (fmt[pos:pos+2] if pos+1 < len(fmt) else fmt[pos])
                msg = f'Unsupported placeholder {ph!r}{err_common}'
                quit_error(msg)
            n = pos + 1
        fmt_simple = fmt.replace('-', '').replace(' ', '')
        esc = re.escape(fmt_simple)
        if esc != fmt_simple:
            char = esc[esc.find('\\')+1]
            msg = f'Bad character {char!r}{err_common}'
            quit_error(msg)

        pat = fmt.replace('%z', r'[+\-]\d{4}(\d\d(\.\d{6})?)?')
        for char in ph_simple:
            count = ('{1,4}' if char == 'Y' else '{1,2}')
            pat = pat.replace(f'%{char}', rf'\d{count}')
        pattern = re.compile(pat)
        date_formats.append((fmt, pattern))
    return date_formats
