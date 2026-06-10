"""네이버 데이터랩 검색어 트렌드 API (강화 버전)"""
import os, requests
from datetime import datetime, timedelta


def _headers():
    return {
        "X-Naver-Client-Id": os.environ.get("NAVER_DATALAB_CLIENT_ID"),
        "X-Naver-Client-Secret": os.environ.get("NAVER_DATALAB_CLIENT_SECRET"),
        "Content-Type": "application/json",
    }


def _check_keys():
    return os.environ.get("NAVER_DATALAB_CLIENT_ID") and os.environ.get("NAVER_DATALAB_CLIENT_SECRET")


def get_search_trend(keyword, days=90):
    """일별 검색 트렌드 (최근 90일)"""
    if not _check_keys():
        return None
    end = datetime.now().strftime("%Y-%m-%d")
    start = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    try:
        resp = requests.post("https://openapi.naver.com/v1/datalab/search",
            headers=_headers(),
            json={"startDate": start, "endDate": end, "timeUnit": "date",
                  "keywordGroups": [{"groupName": keyword, "keywords": [keyword]}]},
            timeout=10)
        resp.raise_for_status()
        data = resp.json().get("results", [])
        if not data or not data[0].get("data"):
            return None
        td = data[0]["data"]
        return {
            "dates": [d["period"] for d in td],
            "values": [round(d["ratio"], 1) for d in td],
            "keyword": keyword,
        }
    except Exception as e:
        print(f"  ⚠️ 데이터랩 트렌드 오류: {e}")
        return None


def get_age_trend(keyword, days=30):
    """연령대별 검색 트렌드 비교 (최근 30일)"""
    if not _check_keys():
        return None
    end = datetime.now().strftime("%Y-%m-%d")
    start = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

    ages = [
        {"name": "20대", "code": "3"},
        {"name": "30대", "code": "4"},
        {"name": "40대", "code": "5"},
        {"name": "50대", "code": "6"},
        {"name": "60대+", "code": "7"},
    ]

    result = {}
    for age in ages:
        try:
            resp = requests.post("https://openapi.naver.com/v1/datalab/search",
                headers=_headers(),
                json={"startDate": start, "endDate": end, "timeUnit": "month",
                      "keywordGroups": [{"groupName": keyword, "keywords": [keyword]}],
                      "ages": [age["code"]]},
                timeout=10)
            resp.raise_for_status()
            data = resp.json().get("results", [])
            if data and data[0].get("data"):
                avg = round(sum(d["ratio"] for d in data[0]["data"]) / len(data[0]["data"]), 1)
                result[age["name"]] = avg
        except:
            continue

    return result if result else None


def get_keyword_comparison(keywords, days=30):
    """키워드 간 검색량 비교 (최대 5개)"""
    if not _check_keys() or not keywords:
        return None
    end = datetime.now().strftime("%Y-%m-%d")
    start = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

    groups = []
    for kw in keywords[:5]:
        groups.append({"groupName": kw, "keywords": [kw]})

    try:
        resp = requests.post("https://openapi.naver.com/v1/datalab/search",
            headers=_headers(),
            json={"startDate": start, "endDate": end, "timeUnit": "date",
                  "keywordGroups": groups},
            timeout=10)
        resp.raise_for_status()
        results = resp.json().get("results", [])
        if not results:
            return None

        comparison = {}
        for r in results:
            name = r["title"]
            if r.get("data"):
                avg = round(sum(d["ratio"] for d in r["data"]) / len(r["data"]), 1)
                comparison[name] = avg

        return comparison
    except Exception as e:
        print(f"  ⚠️ 데이터랩 비교 오류: {e}")
        return None
