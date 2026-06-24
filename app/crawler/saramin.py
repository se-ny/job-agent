import re
from playwright.async_api import async_playwright
from app.crawler.base import BaseCrawler, CrawledJobPost


class SaraminCrawler(BaseCrawler):
    source_name = "saramin"

    SEARCH_URL = "https://www.saramin.co.kr/zf_user/search/recruit?searchword={keyword}"

    async def crawl(self, keyword: str, limit: int = 10) -> list[CrawledJobPost]:
        results: list[CrawledJobPost] = []

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=False,
                args=["--no-sandbox", "--disable-blink-features=AutomationControlled"]
            )
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
            )
            page = await context.new_page()

            url = self.SEARCH_URL.format(keyword=keyword)
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(2000)

            links = await page.eval_on_selector_all(
                ".job_tit a",
                "els => els.map(el => el.href)"
            )

            await browser.close()

        # 각 공고 상세 페이지 크롤링
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=False,
                args=["--no-sandbox", "--disable-blink-features=AutomationControlled"]
            )
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
            )

            for link in links[:limit]:
                try:
                    page = await context.new_page()
                    job = await self.crawl_single(link, page=page)
                    results.append(job)
                    await page.close()
                except Exception as e:
                    print(f"[skip] {link} — {e}")
                    continue

            await browser.close()

        return results

    async def crawl_single(self, url: str, page=None) -> CrawledJobPost:
        close_after = False
        if page is None:
            playwright = await async_playwright().start()
            browser = await playwright.chromium.launch(
                headless=False,
                args=["--no-sandbox", "--disable-blink-features=AutomationControlled"]
            )
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
            )
            page = await context.new_page()
            close_after = True

        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(2000)

        title_el = await page.query_selector("h1.tit_job")
        title = (await title_el.inner_text()).strip() if title_el else "제목 없음"

        company_el = await page.query_selector("a.company")
        company = (await company_el.inner_text()).strip() if company_el else "회사명 없음"

        content_el = await page.query_selector("table.cont_recruit_template")
        raw_text = (await content_el.inner_text()).strip() if content_el else ""
        raw_text = re.sub(r"\n{3,}", "\n\n", raw_text)

        if close_after:
            await page.context.browser.close()

        return CrawledJobPost(
            source=self.source_name,
            title=title,
            company=company,
            raw_text=raw_text,
            url=url,
        )