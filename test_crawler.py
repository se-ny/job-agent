# test_crawler.py
import asyncio
from app.crawler.saramin import SaraminCrawler


async def main():
    crawler = SaraminCrawler()
    jobs = await crawler.crawl("AI 에이전트", limit=3)
    for job in jobs:
        print("=" * 50)
        print(job.title, "-", job.company)
        print(job.raw_text[:200])


if __name__ == "__main__":
    asyncio.run(main())