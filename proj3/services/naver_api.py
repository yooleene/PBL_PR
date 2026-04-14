import os
import requests
from bs4 import BeautifulSoup
import urllib.parse
import html
from concurrent.futures import ThreadPoolExecutor, as_completed

def get_naver_inlink_articles(keyword, display=80, max_articles=25):
    """
    네이버 뉴스 인링크 기사 수집
    - display: 네이버 API 요청 건수 (최대 100, 인링크 필터 후 줄어드므로 넉넉하게)
    - max_articles: 최종 크롤링할 기사 수 (20~25 권장)
    """
    client_id = os.environ.get("NAVER_CLIENT_ID")
    client_secret = os.environ.get("NAVER_CLIENT_SECRET")
    
    enc_text = urllib.parse.quote(keyword)
    url = f"https://openapi.naver.com/v1/search/news.json?query={enc_text}&display={display}&sort=sim"
    
    headers = {
        "X-Naver-Client-Id": client_id,
        "X-Naver-Client-Secret": client_secret
    }
    
    try:
        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            print(f"네이버 API 에러: {response.status_code}")
            return ""
        items = response.json().get('items', [])
    except Exception as e:
        print(f"API 호출 중 에러: {e}")
        return ""
    
    # 인링크 필터링 후 max_articles개
    inlink_items = [item for item in items if "n.news.naver.com" in item['link']]
    target_items = inlink_items[:max_articles]
    
    print(f"  → API 응답 {len(items)}건 중 인링크 {len(inlink_items)}건, 크롤링 대상 {len(target_items)}건")
    
    req_headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    # 병렬 크롤링 (5개씩 동시 → 속도 3~4배 향상)
    def crawl_one(args):
        i, item = args
        link = item['link']
        raw_title = item['title'].replace('<b>', '').replace('</b>', '')
        title = html.unescape(raw_title)
        pub_date = item['pubDate']
        
        try:
            res = requests.get(link, headers=req_headers, timeout=7)
            soup = BeautifulSoup(res.text, 'html.parser')
            body = soup.select_one('#dic_area')
            
            media_elem = soup.select_one('.media_end_head_top_logo img')
            if media_elem and media_elem.has_attr('title'):
                media_name = media_elem['title']
            elif media_elem and media_elem.has_attr('alt'):
                media_name = media_elem['alt']
            else:
                media_name = "알 수 없음"
            
            if body:
                text = body.get_text(separator=' ', strip=True)
                return f"[기사 {i+1}]\n- 제목: {title}\n- 매체: {media_name}\n- 일시: {pub_date}\n- 링크: {link}\n- 본문: {text}"
        except Exception as e:
            print(f"  크롤링 에러 ({link}): {e}")
        return None

    crawled_texts = []
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(crawl_one, (i, item)): i for i, item in enumerate(target_items)}
        for future in as_completed(futures):
            result = future.result()
            if result:
                crawled_texts.append((futures[future], result))
    
    # 원래 순서대로 정렬
    crawled_texts.sort(key=lambda x: x[0])
    
    print(f"  → 크롤링 완료: {len(crawled_texts)}건 성공")
    return "\n\n---\n\n".join(text for _, text in crawled_texts)