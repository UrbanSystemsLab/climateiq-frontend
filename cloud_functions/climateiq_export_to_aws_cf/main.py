from datetime import datetime
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
S3_BUCKET_NAME = "climateiq-data-delivery"

# IDs for retrieving secrets to authenticate to AWS
AWS_ACCESS_KEY_ID = "climasens-aws-access-key-id"
AWS_SECRET_ACCESS_KEY = "climasens-aws-secret-access-key"


@functions_framework.http
def export_to_aws(request: flask.Request) -> tuple[str, int]:
    try:
        prefix = _get_prefix_id(request)
    except ValueError as e:
        return (str(e), 400)

    storage_client = storage.Client()
    blobs_to_export = list(storage_client.list_blobs(GCS_BUCKET_NAME, prefix=prefix))

    if not len(blobs_to_export):
        return (f"No blobs found with prefix {prefix}", 400)

    output_file_dir = datetime.now().strftime("%Y-%m-%d_%H:%M:%S")

    aws_access_key_id = os.environ.get(AWS_ACCESS_KEY_ID)
    aws_secret_access_key = os.environ.get(AWS_SECRET_ACCESS_KEY)

    s3_client = boto3.client(
        "s3",
        aws_access_key_id=aws_access_key_id,
        aws_secret_access_key=aws_secret_access_key,
    )
    for blob in blobs_to_export:
        with blob.open("rb") as fd:
            s3_client.upload_fileobj(
                fd, S3_BUCKET_NAME, f"{output_file_dir}/{blob.name}"
            )
    return ("Success", 200)


def _get_prefix_id(request: flask.Request) -> str:
    prefix = request.args.get("prefix")
    if not prefix:
        raise ValueError("No prefix provided in request parameters.")
    return prefix
