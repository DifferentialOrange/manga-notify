from .basic_rss import BasicRss


class MangaseeRss(BasicRss):
    def is_match(self, url: str) -> bool:
        return 'mangasee' in url
