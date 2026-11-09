import urllib.parse


class APIUrl:
    def __init__(self, url, display):
        self.url = url
        self.display = display

    def format(self, user_display):
        quoted = urllib.parse.quote(user_display, safe='')
        url = self.url.format(user=quoted)
        return url
