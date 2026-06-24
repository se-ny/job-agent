from abc import ABC, abstractmethod
from pydantic import BaseModel


class CrawledJobPost(BaseModel):
    source: str
    title: str
    company: str
    raw_text: str
    url: str


class BaseCrawler(ABC):
    """모든 크롤러가 상속받는 추상 베이스 클래스"""

    source_name: str

    @abstractmethod
    async def crawl(self, keyword: str, limit: int = 10) -> list[CrawledJobPost]:
        """키워드로 검색해서 공고 리스트 반환"""
        raise NotImplementedError

    @abstractmethod
    async def crawl_single(self, url: str) -> CrawledJobPost:
        """단일 공고 URL에서 상세 내용 추출"""
        raise NotImplementedError
    
def get_crawler(source: str) -> BaseCrawler:
    from app.crawler.saramin import SaraminCrawler
    from app.crawler.jobkorea import JobkoreaCrawler

    crawlers = {
        "saramin": SaraminCrawler,
        "jobkorea": JobkoreaCrawler,
    }
    if source not in crawlers:
        raise ValueError(f"지원하지 않는 소스: {source}")
    return crawlers[source]()