from rimadiff.rimadiff_common import RimadiffCommon


class TableCell(RimadiffCommon):
    ALIGN = {'right': '>', 'left': '<', 'center': '^'}

    def __init__(
        self, text, value, row_i, col_i, align='right', bg='black', fg='white',
        bold=False
    ):
        self.text = text
        self.value = value
        self.row_i = row_i
        self.col_i = col_i
        self.align = align
        self.bg = bg
        self.fg = fg
        self.bold = bold

        self.width = -1

    def __str__(self):
        return self.text

    def __len__(self):
        return len(self.text)

    @property
    def is_column_header(self):
        return self.row_i == 0

    @property
    def is_row_header(self):
        return self.col_i == 0

    def print(self):
        color_def = self.term_color(self.bg, self.bold, self.fg)
        align = TableCell.ALIGN[self.align]
        end = ''
        if self.bold:
            end = self.term_color()
        print(f'{color_def} {self.text:{align}{self.width}} {end}', end='')
