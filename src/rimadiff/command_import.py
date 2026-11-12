import json
import os
import shutil
import tempfile
from collections import defaultdict
from datetime import date, datetime
from json import JSONDecodeError
from pathlib import Path

import click

from rimadiff.categories import api_categories
from rimadiff.api_response import APIResponse
from rimadiff.colour_base import ColourBase
from rimadiff.command_common import (
    COMMON_EPILOG, config_dir_option, history_path_option)
from rimadiff.config_reader import ConfigReader
from rimadiff.format_base import FormatBase
from rimadiff.history_manager import HistoryManager
import rimadiff.command_common as command_common

src_type = click.Path(
    exists=True, dir_okay=True, resolve_path=True, path_type=Path)
dest_type = click.Path(
    exists=False, dir_okay=False, resolve_path=True, path_type=Path)


def _get_format_text():
    rows = []
    for _, exts, desc_raw in shutil.get_unpack_formats():
        ext_text = ', '.join(e[1:] for e in exts)
        desc = desc_raw[0].upper() + desc_raw[1:]
        rows.append((ext_text, desc))
    idt = ' '*6
    if not rows:
        return f'{idt}<none supported>'
    max_ext = max(map(len, (r[0] for r in rows)))
    lines = [f'{ext:{max_ext}}  {desc}' for ext, desc in sorted(rows)]
    return idt + f'\n{idt}'.join(lines) + '\n'

import_epilog = """\b
    The supported archive formats for the current Python interpreter are:
""" + _get_format_text()


@click.command(name='import', epilog=(import_epilog + COMMON_EPILOG))
@click.option(
    '-f', '--format', 'format_',
    help='Format of src argument. Defaults to filename extension.'
    )
@click.option(
    '-a', '--api-name', default='main',
    help='Default API name for original API responses.'
    )
@click.option(
    '--encoding', default='utf-8',
    help='Character encoding for reading API responses.'
    )
@click.option(
    '--every-file', is_flag=True,
    help='Do not expect JSON response files to have a .json suffix.'
    )
@click.option(
    '-y', '--yes', is_flag=True,
    help='Skip confirmation.'
    )
@config_dir_option
@history_path_option
@click.argument('src', required=True, type=src_type)
@click.argument('dest', required=False, type=dest_type)
@click.pass_context
def import_(
    ctx, format_, api_name, encoding, every_file, yes, config_dir,
    history_path, src, dest
):
    """
    Import history from JSON file, directory or archive.

    The dest argument specifies a history database file. If not given,
    snapshots will be merged to the currently active history database as
    shown by command "rimadiff path". The the destination database is
    not required to exist. The path src can either be a JSON response
    file, a directory or an archive file with JSON responses from the
    API.

    The directory or archive contents will be read recursively. If the
    relative path of the JSON file contains a date or datetime (e.g.
    "2026-11-01 14:30+0200.json" or "2026-11-01/user.json"), this date
    will be used as the snapshot date. Otherwise the file modify time is
    used. You can add more number-based formats in general configuration
    file key 'import_date_formats'. The username is read directly
    from the JSON files.

    When importing snapshots which were exported earlier with "rimadiff
    export", two keys were added to the JSON response files, 'url' and
    'api_name'. They will be used in the import process. If option
    --api-name is given, this will be used as the default value if one
    is missing from a JSON file. Consult your API URL configuration file
    for valid API names if original API responses for non-Main accounts
    are being imported.

    The tar-based archive formats are treated by the same library and a
    specific type is generally unnecessary. That is to say, specifying
    '-f tar' for a tar.gz archive without a file extension does the job.

    The export command always exports files in utf-8 encoding. For other
    encoding names to use in --encoding option, see valid values from:
    https://docs.python.org/3.11/library/codecs.html#standard-encodings
    """
    config = ConfigReader(config_dir, history_path)
    config.read()

    cmd = CommandMergeHistory(api_name, encoding, every_file, yes)
    if dest is None:
        if config.history_path is None:
            _complain_missing_dest(ctx)
            config.complain_if_no_config()
            return
        dest = config.history_path

    src_type, valid_formats = command_common.determine_file_type(
        src, format_)
    if src_type is None:
        _complain_format_suffix(ctx, format_, src, valid_formats)
        return
    if src_type == 'dir' and format_:
        cmd.complain_format_but_dir()

    cmd.merge(config, src, src_type, dest)


def _complain_missing_dest(ctx):
    click.echo(
        ctx.get_usage() + '\n\n'
        'Error: argument dest is required if there are no config files.'
        )


def _complain_format_suffix(ctx, format_, src, valid_formats):
    end = ''
    if format_:
        msg, what = f'no such format {format_}', 'formats'
    else:
        msg = f'unrecognized src file suffix: {src.suffix[1:]}'
        what = 'suffixes'
        end = '\nUse --format option to specify format.'
    click.echo(
        ctx.get_usage()
        + f'\n\nError: {msg}\n'
        f'Valid {what}: ' + ', '.join(valid_formats)
        + end
        )


class ResponseFileError(Exception):
    pass


class CommandMergeHistory(ColourBase, FormatBase):
    def __init__(self, api_name, encoding, every_file, yes):
        self.default_api = api_name
        self.encoding = encoding
        self.every_file = every_file
        self.skip_confirmation = yes

        self._date_formats = None
        self._size_db_start = None
        self._file_errors = None
        self._has_encoding_error = False

    def complain_format_but_dir(self):
        self.warning(f'\nSrc is a directory, ignoring --format', nl2=False)

    def merge(self, config, src_path, src_type, dest_path):
        # Assigns at top level
        # self._date_formats

        self._date_formats = command_common.get_date_formats(
            config.import_date_formats, self.quit_error)

        files, temp_path = self._get_files_list(src_path, src_type)

        click.echo()
        is_new_db = not dest_path.exists()
        import_count = size_files = None
        proceed = True
        try:
            files.sort(key=lambda f: (
                f.date_ordinal, f.time, f.timezone, f.user_display,
                (f.api_name or ''))
                )

            self._echo_information(
                files, src_path, src_type, dest_path, is_new_db)

            if not self.skip_confirmation:
                proceed = click.confirm('Execute import?')
                click.echo()
            if proceed:
                import_count, size_files = (
                    self._execute_merge(files, src_type, dest_path))
        finally:
            # Clear archive temp directory
            if temp_path:
                shutil.rmtree(temp_path)
            # Remove new empty database
            if not proceed and is_new_db:
                dest_path.unlink()

        if import_count is not None:
            self._echo_import_counts(import_count)
            self._echo_size_differences(
                dest_path, import_count, size_files, src_type)


    def _echo_information(
        self, files, src_path, src_type, dest_path, is_new_db
    ):
        # Assigns
        # self._size_db_start

        info = self._get_files_info(files)
        size_files, users_src_set, user_display_src, api_names_src = info[:4]
        ordinals_src = info[4]

        with HistoryManager(dest_path) as history:
            user_display_db = history.get_user_display_dict()
            users_db_set = {n for n in user_display_db}
            ordinals_db = [t[0] for t in history.get_history_snapshots()]
            api_names_dest = list(history.get_api_category_id_dict())
            history.vacuum()

        if is_new_db:
            size_db = 0
        else:
            size_db = dest_path.stat().st_size
        self._size_db_start = size_db

        # Echo info on src and dest files
        is_archive = (src_type not in ('json', 'dir'))
        archive_path = (src_path if is_archive else None)
        self._echo_info_src_dest(
            src_path, dest_path, archive_path, size_files, size_db, is_new_db,
            len(files)
            )

        # Echo info on users
        users_common = users_src_set & users_db_set
        user_key = lambda u: ((u not in users_common), u)
        users_src = sorted(users_src_set, key=user_key)
        users_db = sorted(users_db_set, key=user_key)
        self._echo_info_users(
            users_src, users_db, user_display_src, user_display_db, is_new_db)

        # Echo info on API names
        self._echo_info_apis(api_names_src, api_names_dest, is_new_db)

        # Echo snapshot dates to import and existing
        ss_src = self._get_snapshot_range(ordinals_src)
        ss_db = self._get_snapshot_range(ordinals_db)
        if is_new_db:
            snapshot_text = f'  {ss_src}'
        else:
            snapshot_text = f'Src:  {ss_src}\nDest: {ss_db}'
        click.echo(
            f'Snapshot dates:\n{snapshot_text}\n'
            )

    def _get_files_info(self, files):
        size_files = 0
        users_src_set = set()
        user_display_src = {}
        api_names_src = set()
        ordinals_src = set()
        for file in files:
            size_files += file.size
            users_src_set.add(file.user)
            user_display_src[file.user] = file.user_display
            api_names_src.add(file.api_name)
            ordinals_src.add(file.date_ordinal)
        return (
            size_files, users_src_set, user_display_src, api_names_src,
            ordinals_src
            )

    def _get_files_list(self, src_path, src_type):
        # Assigns
        # self._file_errors

        init_list = lambda: ['']
        self._file_errors = defaultdict(init_list)

        temp_path = None
        if src_type == 'json':
            files = [self._get_file(src_path)]
        elif src_type == 'dir':
            files = self._get_files_from_directory(src_path)
        else:
            files, temp_path = self._get_files_from_archive(src_path, src_type)

        try:
            if len(self._file_errors) > 0:
                msgs = []
                for type_msg, path_list in self._file_errors.items():
                    msg = type_msg + '\n  '.join(map(str, path_list))
                    msgs.append(msg)
                if self._has_encoding_error:
                    msgs.append(
                        'Check file character encoding and use --encoding '
                        'option.'
                        )
                self.quit_error('\n\n'.join(msgs))
        except:
            if temp_path:
                shutil.rmtree(temp_path)
            raise
        return files, temp_path

    def _get_file(self, path, base_path=None):
        # Assigns
        # self._has_encoding_error

        date_formats = self._date_formats
        file_errors = self._file_errors

        if base_path is None:
            base_path = path.parent
        relpath = path.relative_to(base_path)

        file = None
        try:
            file = ImportFile(path, relpath, date_formats, self.encoding)
        except (
            OSError, JSONDecodeError, ResponseFileError, ValueError
        ) as err:
            msg = f'{type(err).__name__}: {err}'
            file_errors[msg].append(relpath)
            if issubclass(type(err), ValueError):
                self._has_encoding_error = True
        return file

    def _get_files_from_directory(self, src_path):
        files = []
        for dir_str, _, names_str in os.walk(src_path):
            dir_path = Path(dir_str)
            for name in names_str:
                path = dir_path / name
                if self.every_file or path.suffix.lower() == '.json':
                    file = self._get_file(path, src_path)
                    if file:
                        files.append(file)
        return files

    def _get_files_from_archive(self, src_path, src_type):
        file_errors = self._file_errors

        pf = 'rimadiff-import-archive-'
        temp_str = tempfile.mkdtemp(prefix=pf)
        temp_path = Path(temp_str)
        try:
            try:
                shutil.unpack_archive(src_path, temp_path, src_type)
            except OSError as err:
                msg = f'{type(err).__name__}: {err}'
                file_errors[msg].append(src_path)

            files = self._get_files_from_directory(temp_path)
        except:
            shutil.rmtree(temp_path)
            raise
        return files, temp_path

    def _get_snapshot_range(self, ordinals):
        ss_len = len(ordinals)
        if ss_len == 0:
            return '<none>'
        ss_min, ss_max = (self.format_date(date.fromordinal(o))
            for o in (min(ordinals), max(ordinals)))
        pl = ('' if ss_len == 1 else 's')
        return (
            f'{ss_min}'
            + ('' if ss_len == 1 else f' .. {ss_max}')
            + f' ({ss_len} day{pl})'
            )

    def _execute_merge(self, files, src_type, dest_path):
        info = self._get_files_info(files)
        size_files, users_src_set, user_display_src, api_names_src = info[:4]
        ordinals_src = info[4]

        with HistoryManager(dest_path) as history:
            r = self._ensure_dimensions(
                history, files, users_src_set, user_display_src, api_names_src)
            no_config_apis, user_id_dict = r

            overlap_snapshots = self._import_to_database(
                history, files, ordinals_src)

            click.echo('Compacting database...', nl=False)
            history.vacuum()
            click.echo('\rDatabase compacted    \n')

        if no_config_apis:
            api_names = sorted(no_config_apis)
            msg = (
                'Added API names, which are not present in API URL '
                'configuration file:'
                )
            for api_name in api_names:
                msg += f'\n  {api_name}'
            self.warning(msg)

        if overlap_snapshots:
            if len(overlap_snapshots) == len(files):
                self.warning(
                    'All user snapshots had a snapshot for the same date '
                    'already.'
                    )
            else:
                ol_user_ids = {t[0] for t in overlap_snapshots}
                click.echo('Skipped overlapping snapshots:')
                for user_id in ol_user_ids:
                    user = next(
                        u for u, id_ in user_id_dict.items() if id_ == user_id)
                    user_display = user_display_src[user]
                    ordinals = {
                        t[1] for t in overlap_snapshots if t[0] == user_id}
                    date_list = map(date.fromordinal, sorted(ordinals))
                    dates_str = ', '.join(map(self.format_date, date_list))
                    click.echo(f'  {user_display}: {dates_str}')
                click.echo()

        import_count = len(files) - len(overlap_snapshots)
        return import_count, size_files

    def _ensure_dimensions(
        self, history, files, users_src_set, user_display_src, api_names_src
    ):
        no_config_apis = self._ensure_api_category_ids(
            history, files, api_names_src)
        history.ensure_label_data_category_ids()
        user_id_dict = self._ensure_user_ids(
            history, files, users_src_set, user_display_src)
        return no_config_apis, user_id_dict

    def _ensure_api_category_ids(self, history, files, api_names_src):
        api_names = [(n or self.default_api) for n in api_names_src]
        api_id_dict = history.get_api_category_id_dict()

        # Determine missing API categories
        no_config_apis = set()
        add_from_config = []
        add_from_json = []
        for api_name in api_names:
            if api_name not in api_id_dict:
                api_cat = next(
                    (c for c in api_categories if c.name == api_name),
                    None
                    )
                if not api_cat:
                    api_display = api_name.capitalize()
                    add_from_json.append((api_name, api_display))
                    no_config_apis.add(api_name)
                else:
                    add_from_config.append((api_name, api_cat.display))

        # Add categories in a pretty order
        config_names = [c.name for c in api_categories]
        sorted_apis = (
            sorted(add_from_config, key=lambda t: config_names.index(t[0]))
            + sorted(add_from_json)
            )
        for api_name, api_display in sorted_apis:
            id_ = history.add_api_category(api_name, api_display)
            api_id_dict[api_name] = id_

        # Assign File.api_id values
        for file in files:
            api_name = file.api_name or self.default_api
            file.api_id = api_id_dict[api_name]

        return no_config_apis

    def _ensure_user_ids(
        self, history, files, users_src_set, user_display_src
    ):
        user_id_dict = history.get_user_id_dict()
        add_users = [u for u in users_src_set if u not in user_id_dict]

        today_ordinal = date.today().toordinal()
        for user in sorted(add_users):
            user_display = user_display_src[user]
            id_ = history.add_user(user, user_display, today_ordinal)
            user_id_dict[user] = id_

        for file in files:
            file.user_id = user_id_dict[file.user]
        return user_id_dict

    def _import_to_database(self, history, files, ordinals_src):
        snapshots_src = [
            (f.user_id, f.date_ordinal, f.api_id)
            for f in files
            ]
        overlap_snapshots = set() # (user_id, date_ordinal)
        date_width = 0
        zoned_width = 0
        for date_ordinal in ordinals_src:
            user_api_ids = [
                (f.user_id, f.api_id)
                for f in files if f.date_ordinal == date_ordinal
                ]
            snapshot_id_dict = history.get_user_snapshot_id_dict(
                date_ordinal, user_api_ids)
            for user_id in snapshot_id_dict: 
                overlap_snapshots.add((user_id, date_ordinal))

            good_files = [
                f for f in files
                if f.date_ordinal == date_ordinal
                    and f.user_id not in snapshot_id_dict
                ]
            timed_files = defaultdict(list)
            for file in good_files:
                time_tuple = file.date_ordinal, file.time, file.timezone
                timed_files[time_tuple].append(file)

            for time_tuple, file_list in timed_files.items():
                date_ordinal, time, timezone = time_tuple
                dt = date.fromordinal(date_ordinal)
                date_str = self.format_date(dt)
                date_width = max(len(date_str), date_width)
                time_str = ''
                if time:
                    time_str = f' {time}'
                if timezone:
                    time_str += f' ({timezone})'
                dt_str = f'{date_str:>{date_width}}{time_str}'
                zoned_width = max(len(dt_str), zoned_width)

                pl1 = (' ' if len(file_list) == 1 else 's')
                user_count = len({f.user for f in file_list})
                pl2 = ('' if user_count == 1 else 's')
                click.echo(
                    f'Importing snapshot{pl1} at {dt_str:{zoned_width}} - '
                    f'{user_count} user{pl2}'
                    )

                responses = []
                for file in file_list:
                    with file.path.open('r', encoding=self.encoding) as fp:
                        json_obj = json.load(fp)
                    resp = APIResponse(json_obj, file.api_id)
                    resp.user_id = file.user_id
                    responses.append(resp)
                history.write_data(time_tuple, responses, update_info=False)
        return overlap_snapshots

    def _echo_info_src_dest(
        self, src_path, dest_path, archive_path, size_files, size_db,
        is_new_db, len_files
    ):
        size_files_str, size_db_str = map(
            self.format_size, (size_files, size_db))
        if archive_path:
            size_archive = archive_path.stat().st_size
            size_archive_str = self.format_size(size_archive)
            size_files_str = (
                f'archive: {size_archive_str}, extracted: {size_files_str}')
        new_text = ''
        if is_new_db:
            new_text = ' a new'
            size_db_str = ''
        else:
            size_db_str = f' ({size_db_str})'
        num_text = f' {len_files}'
        pl = 's'
        if len_files == 1:
            num_text = pl = ''
        click.echo(
            f'Merging{num_text} file{pl} ({size_files_str}) from:\n'
            f'  {src_path}\n'
            f'Into{new_text} database{size_db_str}:\n  {dest_path}\n'
            )

    def _echo_info_users(
        self, users_src, users_db, user_display_src, user_display_db, is_new_db
    ):
        users_display_src = map(user_display_src.get, users_src)
        users_display_db = map(user_display_db.get, users_db)

        na = ['<none>']
        user_text_src = ', '.join(users_display_src or na)
        if is_new_db:
            users_text = f'  {user_text_src}'
        else:
            users_text = (
                f'Src:  {user_text_src}\n'
                'Dest: ' + ', '.join(users_display_db or na)
                )
        click.echo(f'Users:\n{users_text}\n')

    def _echo_info_apis(self, api_names_src, api_names_dest, is_new_db):
        def api_name_key(name):
            index = next(
                (i for i, c in enumerate(api_categories) if c.name == name),
                len(api_categories)
                )
            return index, name

        api_sorted_src = sorted(
            api_names_src, key=lambda n: api_name_key(n or self.default_api))
        api_text_src = ', '.join(
            (n or f'<default api {self.default_api!r}>')
            for n in api_sorted_src
            )
        if is_new_db:
            api_text = f'  {api_text_src}'
        else:
            api_sorted_dest = sorted(api_names_dest, key=api_name_key)
            api_text_db = ', '.join(api_sorted_dest)
            api_text = f'Src:  {api_text_src}\nDest: {api_text_db}'
        click.echo(f'Importing responses from APIs:\n{api_text}\n')

    def _echo_import_counts(self, import_count):
        count_echo = self.info
        count_text = self.format_number(import_count)
        if import_count == 0:
            count_echo = self.warning
            count_text = 'no'
        pl = ('' if import_count == 1 else 's')
        count_echo(f'Imported {count_text} user snapshot{pl}.')

    def _echo_size_differences(
        self, dest_path, import_count, size_files, src_type
    ):
        size_db_start = self._size_db_start

        if import_count == 0:
            return

        size_db_end = dest_path.stat().st_size

        if size_db_start != 0:
            size_grow = size_db_end - size_db_start
            grow_pct = self.format_percent(size_grow / size_db_start)
            size_grow_str = self.format_size(size_grow)
            click.echo(
                f'Destination database size grew by {grow_pct} '
                f'({size_grow_str})'
                )

        size_files_str, size_db_end_str = map(self.format_size,
            (size_files, size_db_end))

        is_archive = (src_type not in ('json', 'dir'))
        extracted_text = (' (extracted)' if is_archive else '')
        click.echo(
            f'Original JSON size{extracted_text}: {size_files_str}\n'
            f'New database size: {size_db_end_str}\n'
            )


class ImportFile:
    def __init__(self, path, relpath, date_formats, encoding):
        self.path = path
        self.relpath = relpath

        user_display, api_name = self._read_info_from_json(encoding)
        self.user_display = user_display
        self.api_name = api_name

        self.user = self.user_display.strip().lower()

        self._stat = path.stat()
        date_ordinal, time, timezone = self._get_time(date_formats)
        self.date_ordinal = date_ordinal
        self.time = time
        self.timezone = timezone

        self.user_id = None
        self.api_id = None

    @property
    def size(self):
        return self._stat.st_size

    def _read_info_from_json(self, encoding):
        with self.path.open('r', encoding=encoding) as fp:
            obj = json.load(fp)
        user_display = obj.get('name')
        api_name = obj.get('api_name')
        if not user_display:
            msg = f"API response file is missing key 'name'"
            raise ResponseFileError(msg)
        return user_display, api_name

    def _get_time(self, date_formats):
        relpath = str(self.relpath)
        ordinal = time = timezone = None
        dt = None
        for fmt, pattern in date_formats:
            mt = pattern.search(relpath)
            if mt:
                dt = datetime.strptime(mt[0], fmt)
                break
        if not dt:
            mtime = self._stat.st_mtime
            dt = datetime.fromtimestamp(mtime).astimezone()
        if dt:
            ordinal = dt.toordinal()
            time = dt.strftime('%H:%M')
            timezone = dt.strftime('%z')
        return ordinal, time, timezone
