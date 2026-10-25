class RimadiffCommon:
    TERMINAL_COLORS = {
        'white': 107,
        'black': 40,
        'darkgray': '237',
        'green': 42,
        'red': 41,
        'yellow': 103,
        'orange': 43,
        'blue': 104,
    }

    def term_color(self, bg=None, bold=False, fg='white'):
        a = '\033['
        out = a
        a = f'm{a}'
        if bg is None:
            out += '0'
        else:
            if bold:
                out += f'1{a}'

            bg_def = RimadiffCommon.TERMINAL_COLORS[bg]
            if isinstance(bg_def, str):
                out += f'48;5;{bg_def}{a}'
            else:
                out += f'{bg_def}{a}'

            fg_def = RimadiffCommon.TERMINAL_COLORS[fg]
            if isinstance(fg_def, str):
                out += '38;5;{fg_def}'
            else:
                out += f'{fg_def-10}'
        return out + 'm'

    def error(self, msg_err, extra=''):
        msg = str(msg_err)
        if isinstance(msg_err, Exception):
            msg = f'{type(msg_err).__name__}: {msg_err}'
        print(
            self.term_color('black', fg='red') + msg + self.term_color() + '\n'
            )
        if extra:
            print(f'{extra}\n')

    def quit_error(self, msg_err, extra=''):
        print()
        self.error(msg_err, extra)
        quit()

    def warning(self, msg):
        print(
            self.term_color('black', fg='yellow') + str(msg) + self.term_color()
            + '\n'
            )

    def __repr__(self):
        class_name = type(self).__name__
        pub_attrs = ', '.join(
            f'{n}={v!r}'
            for n, v in self.__dict__.items() if not n.startswith('_')
            )
        return f'{class_name}({pub_attrs})'
