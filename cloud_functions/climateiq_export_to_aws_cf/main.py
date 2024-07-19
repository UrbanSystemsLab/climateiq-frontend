from datetime import datetime
import os

import boto3
import flask
import functions_framework
from google.cloud import secretmanager
from google.cloud.storage import client as gcs_client

# GCS bucket name, where merged prediction outputs are stored.
GCS_BUCKET_NAME = (
    os.environ.get("BUCKET_PREFIX", "") + "climateiq-spatialized-merged-predictions"
)
# AWS bucket name, where to copy files to.
S3_BUCKET_NAME = "climateiq-data-delivery"

# IDs for retrieving secrets to authenticate to AWS
PROJECT_ID = "climateiq"
AWS_ACCESS_KEY_ID = "climasens-aws-access-key-id"
AWS_SECRET_ACCESS_KEY = "climasens-aws-secret-access-key"


@functions_framework.http
def export_to_aws(request: flask.Request) -> tuple[str, int]:
    try:
        prefix = _get_prefix_id(request)
    except ValueError as e:
        return (str(e), 400)

    storage_client = gcs_client.Client()
    blobs_to_export = storage_client.list_blobs(GCS_BUCKET_NAME, prefix=prefix)

    if not len(blobs_to_export):
        return (f"No blobs found with prefix {prefix}", 200)

    output_file_dir = datetime.now().strftime("%Y-%m-%d_%H:%M:%S")

    secrets_client = secretmanager.SecretManagerServiceClient()
    try:
        aws_access_key_id = _get_secret_data(secrets_client, AWS_ACCESS_KEY_ID)
        aws_secret_access_key = _get_secret_data(secrets_client, AWS_SECRET_ACCESS_KEY)
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


def _get_secret_data(
    client: secretmanager.SecretManagerServiceClient, secret_id: str
) -> str:
    versions = client.list_secret_versions(
        parent=client.secret_path(PROJECT_ID, secret_id)
    )
    try:
        latest_enabled_version = next(
            version.name for version in versions if version.state == 1
        )
    except StopIteration:
        raise ValueError(f"No enabled versions for found secret {secret_id}.")
    response = client.access_secret_version(name=latest_enabled_version)
    return response.payload.data.decode("UTF-8")
