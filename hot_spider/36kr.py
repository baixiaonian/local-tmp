# -*- coding: utf-8 -*-
import contextlib
import pathlib
import time
import typing
from datetime import datetime

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

url = "https://gateway.36kr.com/api/mis/nav/home/nav/rank/hot"

headers = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36",
}

retries = Retry(
    total=3, backoff_factor=1, status_forcelist=[k for k in range(400, 600)]
)

@contextlib.contextmanager
def request_session():
    s = requests.session()
    try:
        s.headers.update(headers)
        s.mount("http://", HTTPAdapter(max_retries=retries))
        s.mount("https://", HTTPAdapter(max_retries=retries))
        yield s
    finally:
        s.close()

class WebSite36Kr:
    @staticmethod
    def get_raw() -> dict:
        ret = {}
        try:
            payload = {
                "partner_id": "wap",
                "param": {"siteId": 1, "platformId": 2},
                "timestamp": int(time.time()),
            }
            with request_session() as s:
                resp = s.post(url, json=payload)
                ret = resp.json()
        except:
            print("get data failed")
        return ret

    @staticmethod
    def clean_raw(raw_data: dict) -> typing.List[str]:
        return [f"https://36kr.com/p/{item['itemId']}" 
                for item in raw_data["data"]["hotRankList"]]

    @staticmethod
    def save_urls(urls: typing.List[str], dir_name: str) -> None:
        pathlib.Path("./res").mkdir(exist_ok=True)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_path = f"./res/{dir_name}_{timestamp}_urls.txt"
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(urls))

    def run(self):
        raw_data = self.get_raw()
        urls = self.clean_raw(raw_data)
        self.save_urls(urls, "36kr")

if __name__ == "__main__":
    website_36kr_obj = WebSite36Kr()
    website_36kr_obj.run()