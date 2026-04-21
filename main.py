import gspread
from playwright.sync_api import sync_playwright, Page, Locator, ViewportSize
from playwright_stealth import Stealth
from typing import List, Set

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
        self.seen_texts: Set[str] = set()

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
            except Exception:
                pass

    def run(self, max_posts: int = 30) -> None:
        """Main scraping loop."""
        stealth_config = Stealth()

        with sync_playwright() as p:
            context = p.chromium.launch_persistent_context(
                "user_data",
                headless=self.headless, # Keep False to handle manual login/check
                slow_mo=500,            # Human-like delay
                viewport=ViewportSize(width=1280, height=1080)
            )
            page: Page = context.new_page()
            page.goto(self.group_url)

            print(f"Targeting: {self.group_url}")
            page.wait_for_selector('div[role="feed"]', timeout=160000)

            seen_texts = set()
            reached_target_date = False

            while not reached_target_date:
                locator = page.locator('div[data-ad-rendering-role="story_message"]')
                total: int = locator.count()
                print(f"目前找到 {total} 則貼文，已儲存 {len(self.scraped_posts)} 則")

                for i in range(total):
                    try:
                        container = locator.nth(i)

                        # 找標題
                        title_el = container.locator("strong").first
                        title_text = title_el.inner_text(timeout=5000).strip() if title_el.count() > 0 else "無標題"

                        # 展開「查看更多」
                        see_more_btn = container.locator('div[role="button"]').first
                        if see_more_btn.count() > 0 and see_more_btn.is_visible(timeout=5000):
                            see_more_btn.click()
                            page.wait_for_timeout(1500)

                        # 抓完整內文，去重
                        story_content = container.inner_text(timeout=5000).strip()
                        if story_content[:150] in seen_texts:
                            continue
                        seen_texts.add(story_content[:150])

                        # 懸停取得精確時間
                        big_box = container.locator('xpath=./../../..')
                        time_link = big_box.locator('div.html-div span span.html-span a[role="link"]').first
                        post_time = "未知時間"
                        if time_link.count() > 0:
                            time_link.hover()
                            page.wait_for_timeout(800)
                            tooltip = page.locator('div[role="tooltip"]').first
                            if tooltip.count() > 0:
                                post_time = tooltip.inner_text().strip()
                            else:
                                post_time = time_link.get_attribute("aria-label") or "未知時間"

                        self.scraped_posts.append([title_text, story_content, post_time])
                        print(f"  已儲存第 {len(self.scraped_posts)} 則：{title_text[:20]}...")


                    except Exception as e:
                        print(f"Fail: {e}")
                        continue

                # 往下滾動，等新貼文載入
                page.mouse.wheel(0, 2000)
                page.wait_for_timeout(3000)

                # 停止條件：之後可改為比對 TARGET_DATE
                if len(self.scraped_posts) > max_posts:
                    reached_target_date = True

            print(f"Finished. Scraped {len(self.scraped_posts)} posts.")
            context.close()

            # Upload to Google Sheet
            self._upload_to_sheet()

    def _upload_to_sheet(self) -> None:
        """Appends the scraped data to the Google Sheet."""
        if not self.scraped_posts:
            print("No data found to upload.")
            return

        print(f"Uploading {len(self.scraped_posts)} rows to '{self.sheet_name}'...")
        self.worksheet.append_rows(self.scraped_posts)
        print("Upload complete!")


if __name__ == "__main__":
    # --- CONFIGURATION ---
    # GROUP_URL = "https://www.facebook.com/groups/NCCUSTUDENT"
    GROUP_URL = "https://www.facebook.com/groups/385397094898737"

    scraper = FacebookScraper(
        group_url=GROUP_URL,
        sheet_name="FBGroup"
    )
    scraper.run(max_posts=30)
