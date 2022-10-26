from .basic_mangakakalot_bs import BasicMangakakalotBs

class MangaNatoBs(BasicMangakakalotBs):
    def is_match(self, url: str) -> bool:
        return 'chapmanganato' in url
