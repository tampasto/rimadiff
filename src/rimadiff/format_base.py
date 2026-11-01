class FormatBase:
    def format_number(self, value, show_plus=False):
        sign = ('+' if show_plus and value > 0 else '')
        text = f'{value:{sign},}'.replace(',', ' ')
        return text

    def format_size(self, size):
        if size/10 > 1024**3:
            return f'{size//1024**3}G'
        elif size/10 > 1024**2:
            return f'{size//1024**2}M'
        elif size/10 > 1024:
            return f'{size//1024}k'
        return f'{size}'
