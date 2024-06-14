import collections
import csv
import re

import flask
from google.cloud import storage
import functions_framework


# Bucket name, where prediction outputs are stored.
BUCKET_NAME = "climateiq-predictions"
# File name pattern for the CSVs for each scenario and chunk.
CHUNK_FILE_NAME_PATTERN = (
    r"(?P<run_id>\w+)/(?P<prediction_type>\w+)/(?P<model_id>\w+)/"
    r"(?P<study_area_name>\w+)/(?P<scenario_id>\w+)/(?P<chunk_id>\w+)\.csv"
)
# Directory in bucket to write merged files.
OUTPUT_DIR = "merged"


# This only handles merging flood data. Heat data will be divided into completely
# different chunks.
@functions_framework.http
def merge_scenario_predictions(request: flask.Request) -> tuple[str, int]:
    try:
        run_id, prediction_type, model_id, study_area_name = _get_args(
            request, ("run_id", "prediction_type", "model_id", "study_area_name")
        )
    except ValueError as error:
        return f"Bad request: {error}", 400

    storage_client = storage.Client()
    bucket = storage_client.bucket(BUCKET_NAME)

    blobs = storage_client.list_blobs(
        BUCKET_NAME, f"{run_id}/{prediction_type}/{model_id}/{study_area_name}"
    )
    chunk_ids, scenario_ids = _get_chunk_and_scenario_ids(blobs)
    for chunk_id in chunk_ids:
        output_file_name = (
            f"{OUTPUT_DIR}/{run_id}/{study_area_name}/{prediction_type}/{chunk_id}.csv"
        )
        blob_to_write = bucket.blob(output_file_name)
        with blob_to_write.open("w") as fd:
            writer = csv.DictWriter(fd, fieldnames=["h3_index"] + scenario_ids)
            writer.writeheader()
            predictions_by_h3_index: dict[str, dict] = collections.defaultdict(dict)
            for scenario_id in scenario_ids:
                object_name = (
                    f"{run_id}/{prediction_type}/{model_id}/"
                    f"{study_area_name}/{scenario_id}/{chunk_id}.csv"
                )
                for row in _get_file_content(bucket, object_name):
                    predictions_by_h3_index[row["h3_index"]][scenario_id] = row[
                        "prediction"
                    ]
            for h3_index, predictions in predictions_by_h3_index.items():
                predictions["h3_index"] = h3_index
                # Output CSV will have the headers: h3_index, scenario_0, scenario_1...
                writer.writerow(predictions)
    return "Success", 200


def _get_args(
    request: flask.Request, arg_names: collections.abc.Iterable[str]
) -> list[str]:
    args = []
    for arg_name in arg_names:
        arg_value = request.args.get(arg_name)
        if not arg_value:
            raise ValueError(f"Missing arg {arg_name}")
        args.append(arg_value)
    return args


def _get_chunk_and_scenario_ids(
    blobs: list[storage.Blob],
) -> tuple[list[str], list[str]]:
    chunk_ids = set()
    scenario_ids = set()
    for blob in blobs:
        match = re.match(CHUNK_FILE_NAME_PATTERN, blob.name)
        # Ignore blobs that don't match the pattern.
        if not match:
            continue
        chunk_ids.add(match.group("chunk_id"))
        scenario_ids.add(match.group("scenario_id"))
    return sorted(list(chunk_ids), key=str), sorted(list(scenario_ids), key=str)


def _get_file_content(bucket: storage.Bucket, object_name: str) -> list[dict]:
    blob = bucket.blob(object_name)
    # If the specific blob doesn't exist (i.e., no prediction for given scenario_id and
    # chunk_id), then just skip it.
    if not blob.exists():
        return []
    with blob.open() as fd:
        return list(csv.DictReader(fd))
