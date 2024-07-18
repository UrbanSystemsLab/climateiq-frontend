from datetime import datetime
import os

import boto3
import flask
import functions_framework
from google.cloud import firestore, storage

# GCS bucket name, where merged prediction outputs are stored.
GCS_BUCKET_NAME = (
    os.environ.get("BUCKET_PREFIX", "") + "climateiq-spatialized-merged-predictions"
)
# AWS bucket name, where to copy files to.
S3_BUCKET_NAME = "climateiq-data-delivery"

# IDs for Firestore.
SECRET_KEYS_COLLECTION_ID = "secret_keys"
AWS_KEYS_DOC_ID = "aws_keys"
AWS_ACCESS_KEY_ID_KEY = "aws_access_key_id"
AWS_SECRET_ACCESS_KEY_KEY = "aws_secret_access_key"


@functions_framework.http
def export_to_aws(request: flask.Request) -> tuple[str, int]:
    try:
        prefix = _get_prefix_id(request)
    except ValueError as e:
        return (str(e), 400)

    storage_client = storage.Client()
    blobs_to_export = storage_client.list_blobs(GCS_BUCKET_NAME, prefix=prefix)

    output_file_dir = datetime.now().strftime("%Y-%m-%d_%H:%M:%S")

    try:
        aws_access_key_id, aws_secret_access_key = _get_aws_access_keys()
    except ValueError as e:
        return (str(e), 500)

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


def _get_aws_access_keys() -> tuple[str, str]:
    db = firestore.Client()
    aws_keys_doc = (
        db.Collection(SECRET_KEYS_COLLECTION_ID).document(AWS_KEYS_DOC_ID).get()
    )

    if not aws_keys_doc.exists:
        raise ValueError("AWS keys not found in Firestore.")

    return (
        aws_keys_doc.get(AWS_ACCESS_KEY_ID_KEY),
        aws_keys_doc.get(AWS_SECRET_ACCESS_KEY_KEY),
    )
