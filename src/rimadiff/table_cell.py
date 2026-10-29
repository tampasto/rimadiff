import click

from rimadiff.rimadiff_common import RimadiffCommon

NOT_SET = object()


class TableCell(RimadiffCommon):
    ALIGN = {'right': '>', 'left': '<', 'center': '^'}

    def __init__(self, text, value=NOT_SET):
        self.text = str(text)
        if value is NOT_SET:
            self.value = text
        else:
            self.value = value
        self.style_classes = []

    def __str__(self):
        return self.text

    def get_coloured(
        self, table_type, table_name, width, align_name, style_classes
    ):
        align = TableCell.ALIGN[align_name]
        sdict = self.get_style(table_type, 'default', table_name) or {}
        for name in (style_classes + self.style_classes):
            sdict |= self.get_style(table_type, name, table_name) or {}

        styled = self.click_style(f' {self.text:{align}{width}} ', sdict)
        return styled
