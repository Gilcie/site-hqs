import logging
import time

import feeder
import jobs_db
from comics_lib import series_dest_dir

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("feeder_worker")

POLL_INTERVAL_SECONDS = 5


def process_one(link_id, url, publisher, series, position):
    dest_dir = series_dest_dir(publisher, series)

    def on_progress(done, total):
        jobs_db.update_link_progress(link_id, done, total)

    try:
        path = feeder.download_link(url, dest_dir, on_progress=on_progress, position=position)
        jobs_db.update_link_status(link_id, "done", filename=path.name)
        log.info("done: %s -> %s", url, path)
    except feeder.FeederError as e:
        jobs_db.update_link_status(link_id, "error", error_msg=str(e))
        log.warning("error: %s (%s)", url, e)
    except Exception as e:
        jobs_db.update_link_status(link_id, "error", error_msg="Falha inesperada: {}".format(e))
        log.exception("unexpected failure downloading %s", url)


def main():
    jobs_db.init_db()
    log.info("feeder_worker started, polling every %ss", POLL_INTERVAL_SECONDS)
    while True:
        claimed = jobs_db.claim_next_pending_link()
        if claimed is None:
            time.sleep(POLL_INTERVAL_SECONDS)
            continue
        process_one(*claimed)


if __name__ == "__main__":
    main()
