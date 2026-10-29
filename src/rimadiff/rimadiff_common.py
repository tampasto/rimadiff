import click


class RimadiffCommon:
    colour_scheme = None
    _colour_warnings = set()

    def get_style(self, type_, name, subkey=None):
        sdict = None
        scheme = RimadiffCommon.colour_scheme
        if not scheme:
            return {}

        type_table = scheme.get(type_)
        if not isinstance(type_table, dict):
            return {}

        sdict = type_table.get(name)
        if not isinstance(sdict, dict):
            sdict = {}
        else:
            sdict = sdict.copy()

        if subkey:
            sk_table = type_table.get(subkey)
            if isinstance(sk_table, dict):
                sdict |= sk_table
        return sdict

    def error(self, msg_err, extra=''):
        msg = str(msg_err)
        if isinstance(msg_err, Exception):
            msg = f'{type(msg_err).__name__}: {msg_err}'

        sdict = self.get_style('message', 'error')
        styled = self.click_style(f'{msg}\n', sdict)
        click.echo(styled)

        if extra:
            click.echo(f'{extra}\n')

    def quit_error(self, msg_err, extra=''):
        click.echo()
        self.error(msg_err, extra)
        quit()

    def warning(self, msg):
        sdict = self.get_style('message', 'warning')
        styled = self.click_style(f'{msg}\n', sdict)
        click.echo(styled)

    def info(self, msg):
        sdict = self.get_style('message', 'info')
        styled = self.click_style(f'{msg}\n', sdict)
        click.echo(styled)

    def click_style(self, text, sdict):
        styled = text
        try:
            styled = click.style(styled, **sdict)
        except (ValueError, TypeError) as err:
            msg = str(err)
            if type(err) == TypeError:
                msg = msg.replace('style() got a', 'A')
                msg = msg.replace('keyword argument', 'style specifier')
            RimadiffCommon._colour_warnings.add(msg)
        return styled

    @classmethod
    def print_colour_warnings(cls):
        if cls._colour_warnings:
            pl = ('' if len(cls._colour_warnings) == 1 else 's')
            click.echo(f'Error{pl} in colour configuration:')
            for text in sorted(cls._colour_warnings):
                click.echo(f'  {text}')
            click.echo()

    def __repr__(self):
        class_name = type(self).__name__
        pub_attrs = ', '.join(
            f'{n}={v!r}'
            for n, v in self.__dict__.items() if not n.startswith('_')
            )
        return f'{class_name}({pub_attrs})'
