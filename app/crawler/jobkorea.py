import re
from playwright.async_api import async_playwright
from app.crawler.base import BaseCrawler, CrawledJobPost


class JobkoreaCrawler(BaseCrawler):
    source_name = "jobkorea"

    SEARCH_URL = "https://www.jobkorea.co.kr/Search/?stext={keyword}"

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
                "a[href*='/Recruit/GI_Read/']",
                "els => [...new Set(els.map(el => el.href))]"
            )

            await browser.close()

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

        # 회사명
        company_el = await page.query_selector("h2.font-medium")
        company = (await company_el.inner_text()).strip() if company_el else "회사명 없음"

        # 제목
        title_el = await page.query_selector("h1.font-bold")
        title = (await title_el.inner_text()).strip() if title_el else "제목 없음"

        # 본문 — iframe 안 div.recruitment
        raw_text = ""
        frame_el = await page.query_selector("iframe#parent_frame, iframe[id*='frame']")
        if frame_el:
            frame = await frame_el.content_frame()
            if frame:
                await frame.wait_for_timeout(1000)
                recruitment_el = await frame.query_selector("div.recruitment")
                if recruitment_el:
                    raw_text = (await recruitment_el.inner_text()).strip()
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