import os

PREDICTIONS_BUCKET = os.environ.get("BUCKET_PREFIX", "") + "climateiq-predictions"
CHUNK_PREDICTIONS_BUCKET = (
    os.environ.get("BUCKET_PREFIX", "") + "climateiq-chunk-predictions"
)
SPATIALIZED_CHUNK_PREDICTIONS_BUCKET = (
    os.environ.get("BUCKET_PREFIX", "") + "climateiq-spatialized-chunk-predictions"
)
SPATIALIZED_MERGED_PREDICTIONS_BUCKET = (
    os.environ.get("BUCKET_PREFIX", "") + "climateiq-spatialized-merged-predictions"
)
