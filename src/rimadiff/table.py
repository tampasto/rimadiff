from rimadiff.rimadiff_common import RimadiffCommon

import click


class Table(RimadiffCommon):
    ERR_INSERT_LEN = (
        'Inserting row of {} cells to table of {} cell rows in {}.')

    def __init__(
        self, name, type_, column_headers=None, column_align=None,
        has_row_headers=False
    ):
        self.name = name
        self.type = type_
        self.column_align = column_align

        self._cells = []
        self._column_width = None

        self.has_row_headers = has_row_headers
        self.has_column_headers = False
        if column_headers:
            self.add_row(column_headers)
            self.has_column_headers = True

        # Can be assigned after init
        self.styled_row = {}
        self.styled_column = {}

    def add_row(self, row):
        col_width = self._column_width
        if col_width is None:
            self._column_width = [len(c.text) for c in row]
        else:
            this_len = len(row)
            last_len = len(self._cells[-1])
            if this_len != last_len:
                msg = Table.ERR_INSERT_LEN.format(
                    this_len, last_len, f'{self.type}.{self.name}')
                raise Exception(msg)
            for col_i, cell in enumerate(row):
                col_width[col_i] = max(len(cell.text), col_width[col_i])
        self._cells.append(row)

    @property
    def height(self):
        if self._cells:
            return len(self._cells)
        return 0

    @property
    def width(self):
        if self._column_width:
            return sum(n+2 for n in self._column_width)
        return 0

    def render_lines(self):
        lines = []
        table_type = self.type
        col_width = self._column_width
        col_align = self.column_align
        has_col_header = self.has_column_headers
        has_row_header = self.has_row_headers
        stripe_start = int(has_col_header)
        styled_row = self.styled_row
        styled_col = self.styled_column

        for row_i, row in enumerate(self._cells):
            line = ''
            for col_i, cell in enumerate(row):
                width = col_width[col_i]
                align = (col_align[col_i] if col_align else 'right')
                is_stripe = ((row_i - stripe_start) % 2 == 0)

                style_classes = []
                if is_stripe:
                    style_classes.append('stripe')

                if has_col_header and row_i == 0:
                    style_classes.append('column_header')
                elif has_row_header and col_i == 0:
                    style_classes.append('row_header')
                    if is_stripe:
                        style_classes.append('row_header_stripe')

                if (has_col_header and has_row_header
                    and row_i == 0 and col_i == 0):
                    # Is table header cell in left top corner
                    style_classes.append('table_header')

                specials = [(row_i, styled_row), (col_i, styled_col)]
                for dim_i, dim_dict in specials:
                    name = dim_dict.get(dim_i)
                    if name:
                        if 'column_header' in style_classes:
                            style_classes.append(f'{name}_header')
                        else:
                            style_classes.append(name)

                line += cell.get_coloured(
                    table_type, width, align, style_classes)

            lines.append(line)
        return lines

    def echo(self):
        lines = self.render_lines()
        for line in lines:
            click.echo(line)
        click.echo()
