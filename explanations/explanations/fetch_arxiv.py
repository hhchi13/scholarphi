import logging
import os

import requests

from explanations.directories import SOURCE_ARCHIVES_DIR, source_archives

USER_AGENT = "Andrew Head, for academic research on dissemination of scientific insight <head.andrewm@gmail.com>"


def save_source_archive(arxiv_id: str, content: bytes):
    if not os.path.exists(SOURCE_ARCHIVES_DIR):
        os.makedirs(SOURCE_ARCHIVES_DIR)
    archive_path = source_archives(arxiv_id)
    with open(archive_path, "wb") as archive:
        archive.write(content)


def fetch(arxiv_id: str):
    logging.debug("Fetching sources.")
    uri = "https://arxiv.org/e-print/%s" % (arxiv_id,)
    response = requests.get(uri, headers={"User-Agent": USER_AGENT})
    save_source_archive(arxiv_id, response.content)
