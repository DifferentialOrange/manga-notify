from .basic_mangakakalot_bs import BasicMangakakalotBs

class MangakakalotBs(BasicMangakakalotBs):
    def is_match(self, url: str) -> bool:
        return 'mangakakalot' in url
