import sys
from deepkt.crawler import extract_artist_urls
try:
    urls = extract_artist_urls("https://soundcloud.com/lxst_cxntury", num_tracks=130)
    print("SUCCESS", len(urls))
except Exception as e:
    print("ERROR", str(e))
