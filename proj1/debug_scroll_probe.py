from playwright.sync_api import sync_playwright

import app


with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(
        locale="ko-KR",
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
    )
    page.goto(app.build_office_search_url("1081"), wait_until="domcontentloaded", timeout=25000)
    page.wait_for_timeout(1200)
    app.apply_reporter_option(page, "김지예", lambda _p, _m: None)
    page.wait_for_timeout(1000)
    last_height = 0
    stable = 0
    for idx in range(30):
        articles = app.extract_articles_from_html(page.content(), "김지예", "서울신문")
        height = page.evaluate("() => document.documentElement.scrollHeight")
        print(idx, "count", len(articles), "height", height)
        page.mouse.wheel(0, 2200)
        page.wait_for_timeout(900)
        if height == last_height:
            stable += 1
        else:
            stable = 0
        last_height = height
        if stable >= 4:
            break
    articles = app.extract_articles_from_html(page.content(), "김지예", "서울신문")
    with open("debug_seoul_kim.html", "w", encoding="utf-8") as handle:
        handle.write(page.content())
    print("final", len(articles))
    for article in articles[:30]:
        print("-", article.title)
    browser.close()
