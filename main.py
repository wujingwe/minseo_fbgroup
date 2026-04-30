from typing import List
import os

import gspread
from playwright.sync_api import sync_playwright, Page, Locator, ViewportSize
from playwright_stealth import Stealth


def read_properties(filepath: str = 'local.properties') -> dict:
    """Read key=value pairs from a local.properties file."""
    config = {}
    if not os.path.exists(filepath):
        return config

    with open(filepath, 'r') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#'):
                if '=' in line:
                    key, value = line.split('=', 1)
                    config[key.strip()] = value.strip()
    return config


class FacebookScraper:
    def __init__(
            self,
            group_url: str,
            sheet_name: str,
            credentials_path: str = 'credentials.json',
            headless: bool = False
    ) -> None:
        self.group_url = group_url
        self.sheet_name = sheet_name
        self.credentials_path = credentials_path
        self.headless = headless

        # Scraper state: A list of rows (each row is a list of strings)
        self.scraped_posts: List[List[str]] = []

        # Initialize Google Sheets types
        self.gc: gspread.Client = gspread.service_account(filename=self.credentials_path)
        self.spreadsheet: gspread.Spreadsheet = self.gc.open(self.sheet_name)
        self.worksheet: gspread.Worksheet = self.spreadsheet.sheet1

    @staticmethod
    def _get_timestamp(
            container: Locator,
            page: Page
    ) -> str:
        """Extracts the precise post time via hover."""
        try:
            big_box: Locator = container.locator('xpath=./../../..')
            time_link: Locator = big_box.locator('div.html-div span span.html-span a[role="link"]').first

            if time_link.count() > 0:
                time_link.hover()
                page.wait_for_timeout(800)
                tooltip: Locator = page.locator('div[role="tooltip"]').first

                if tooltip.count() > 0:
                    return tooltip.inner_text().strip()
                return str(time_link.get_attribute("aria-label") or "未知時間")
        except Exception as e:
            print(f"未知時間: {e}")
            return "未知時間"
        return "未知時間"

    @staticmethod
    def _expand_content(container: Locator, page: Page) -> None:
        """Clicks 'See More' to ensure full text is scraped."""
        see_more_btn: Locator = container.locator('div[role="button"]').first
        if see_more_btn.count() > 0 and see_more_btn.is_visible(timeout=2000):
            try:
                see_more_btn.click()
                page.wait_for_timeout(1000)
            except Exception as e:
                print(f"Fail to expand content: {e}")
                pass

    def run(self, max_posts: int = 30, batch_size: int = 10) -> None:
        """Main scraping loop."""
        stealth = Stealth()
        with sync_playwright() as p:
            context = p.chromium.launch_persistent_context(
                "user_data",
                headless=self.headless,  # Keep False to handle manual login/check
                slow_mo=500,  # Human-like delay
                viewport=ViewportSize(width=1280, height=1080),
                args=['--disable-images', '--disable-fonts']
            )
            page: Page = context.new_page()
            stealth.apply_stealth_sync(page)
            context.route(
                "**/*",
                lambda route: route.abort() if (
                        route.request.resource_type in ["image", "media", "font"] or
                        route.request.url.endswith(('.mp4', '.webm', '.ogg', '.mov', '.avi'))
                ) else route.continue_()
            )
            page.goto(self.group_url)

            print(f"Targeting: {self.group_url}")
            page.wait_for_selector('div[role="feed"]', timeout=160000)

            seen_texts = set()
            reached_max_posts = False
            total_scraped = 0

            while not reached_max_posts:
                locator = page.locator('div[data-ad-rendering-role="story_message"]')
                total: int = locator.count()
                print(f"目前找到 {total} 則貼文，已儲存 {total_scraped} 則")

                for i in range(total):
                    try:
                        container = locator.nth(i)

                        # 找標題
                        title_el = container.locator("strong").first
                        title_text = title_el.inner_text(timeout=5000).strip() if title_el.count() > 0 else "無標題"

                        # 展開「查看更多」
                        self._expand_content(container, page)

                        # 抓完整內文，去重
                        story_content = container.inner_text(timeout=5000).strip()
                        if story_content[:150] in seen_texts:
                            continue
                        seen_texts.add(story_content[:150])

                        # 懸停取得精確時間
                        post_time = self._get_timestamp(container, page)

                        self.scraped_posts.append([title_text, story_content, post_time])
                        total_scraped += 1
                        print(f"  已儲存第 {total_scraped} 則：{title_text[:20]}...")

                        # Batch upload check
                        if len(self.scraped_posts) >= batch_size:
                            print(f"Uploading batch of {len(self.scraped_posts)} posts...")
                            try:
                                self._upload_to_sheet()
                                self.scraped_posts.clear()
                            except Exception as e:
                                print(f"Batch upload failed: {e}. Will retry later.")


                    except Exception as e:
                        print(f"Fail: {e}")
                        continue

                # 往下滾動，等新貼文載入
                page.mouse.wheel(0, 2000)
                page.wait_for_timeout(3000)

                # 停止條件：之後可改為比對 TARGET_DATE
                if total_scraped >= max_posts:
                    reached_max_posts = True

            # Upload any remaining posts
            if self.scraped_posts:
                print(f"Uploading remaining {len(self.scraped_posts)} posts...")
                try:
                    self._upload_to_sheet()
                except Exception as e:
                    print(f"Final upload failed: {e}")

            print(f"Finished. Scraped {total_scraped} posts.")
            context.close()

    def _upload_to_sheet(self) -> None:
        """Appends the scraped data to the Google Sheet."""
        if not self.scraped_posts:
            print("No data found to upload.")
            return

        print(f"Uploading {len(self.scraped_posts)} rows to '{self.sheet_name}'...")
        self.worksheet.append_rows(self.scraped_posts)
        print("Upload complete!")


if __name__ == "__main__":
    # Read configuration from local.properties (if exists)
    config = read_properties('local.properties')

    GROUP_URL = config.get('GROUP_URL', 'https://www.facebook.com/groups/NCCUSTUDENT')
    SHEET_NAME = config.get('SHEET_NAME', 'FBGroup')
    CREDENTIALS_PATH = config.get('CREDENTIALS_PATH', 'credentials.json')
    HEADLESS = config.get('HEADLESS', 'false').lower() == 'true'
    MAX_POSTS = int(config.get('MAX_POSTS', '200'))
    BATCH_SIZE = int(config.get('BATCH_SIZE', '10'))

    print(f"Configuration loaded: URL={GROUP_URL[:50]}..., Sheet={SHEET_NAME}")

    scraper = FacebookScraper(
        group_url=GROUP_URL,
        sheet_name=SHEET_NAME,
        credentials_path=CREDENTIALS_PATH,
        headless=HEADLESS
    )
    scraper.run(max_posts=MAX_POSTS, batch_size=BATCH_SIZE)
