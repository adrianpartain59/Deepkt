import sys
from deepkt.crawler import extract_artist_urls
from deepkt.pipeline import run_pipeline
from deepkt.indexer import rebuild_search_index

try:
    urls = extract_artist_urls("https://soundcloud.com/lxst_cxntury", num_tracks=130)
    print("Extracted", len(urls), "urls")
    run_pipeline(urls=urls, resume=False)
    rebuild_search_index()
    print("SUCCESS")
except Exception as e:
    import traceback
    traceback.print_exc()
