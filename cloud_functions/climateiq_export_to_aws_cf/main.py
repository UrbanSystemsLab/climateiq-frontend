from datetime import datetime
import logging
import os

import boto3
import flask
import functions_framework
from google.cloud import storage

# GCS bucket name, where merged prediction outputs are stored.
GCS_BUCKET_NAME = (
    os.environ.get("BUCKET_PREFIX", "") + "climateiq-spatialized-merged-predictions"
)
# AWS bucket name, where to copy files to.
S3_BUCKET_NAME = (
    "climateiq-data-delivery-dev"
    if os.environ.get("BUCKET_PREFIX", "").startswith("test")
    else "climateiq-data-delivery"
)

# IDs for retrieving secrets to authenticate to AWS
AWS_ACCESS_KEY_ID = "climasens-aws-access-key-id"
AWS_SECRET_ACCESS_KEY = "climasens-aws-secret-access-key"


@functions_framework.http
def export_to_aws(request: flask.Request) -> tuple[str, int]:
    try:
        prefix = _get_prefix_id(request)
    except ValueError as e:
        return (str(e), 400)

    logging.info(
        f"Starting export of files under {GCS_BUCKET_NAME}/{prefix} to "
        f"{S3_BUCKET_NAME}..."
    )

    storage_client = storage.Client()
    blobs_to_export = list(storage_client.list_blobs(GCS_BUCKET_NAME, prefix=prefix))

    total_blobs = len(blobs_to_export)

    if not total_blobs:
        return (f"No blobs found with prefix {prefix}\n", 400)

    curr_time_str = datetime.now().strftime("%Y-%m-%d_%H:%M:%S")

    aws_access_key_id = os.environ.get(AWS_ACCESS_KEY_ID)
    aws_secret_access_key = os.environ.get(AWS_SECRET_ACCESS_KEY)

    s3_client = boto3.client(
        "s3",
        aws_access_key_id=aws_access_key_id,
        aws_secret_access_key=aws_secret_access_key,
    )
    for i, blob in enumerate(blobs_to_export):
        logging.info(f"Exporting {blob.name} ({i + 1}/{total_blobs})...")
        with blob.open("rb") as fd:
            s3_client.upload_fileobj(fd, S3_BUCKET_NAME, f"{curr_time_str}/{blob.name}")
            blob.metadata = {"export_time": curr_time_str}
            blob.patch()
        logging.info(f"Successfully exported {blob.name} ({i + 1}/{total_blobs}).")
    return (f"Successfully exported {total_blobs} CSV files to ClimaSens.\n", 200)


def _get_prefix_id(request: flask.Request) -> str:
    req_json = request.get_json(silent=True)
    if req_json is None or "prefix" not in req_json:
        raise ValueError("No prefix provided in request.\n")
    return req_json["prefix"]
