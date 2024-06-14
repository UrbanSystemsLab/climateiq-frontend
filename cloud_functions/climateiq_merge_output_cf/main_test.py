import re
import tempfile
import typing

import flask
from google.cloud import storage
import pytest
from unittest import mock

import main


# Create a fake "app" for generating test request contexts.
@pytest.fixture(scope="module")
def app():
    return flask.Flask(__name__)


# Create a temporary directory for test files. Dir will be deleted after each test.
@pytest.fixture(scope="module")
def tmpdir():
    return tempfile.TemporaryDirectory()


def _create_chunk_file(h3_indices_to_predictions, tmpdir):
    rows = ["h3_index,prediction"] + [
        f"{h3_index},{prediction}"
        for h3_index, prediction in h3_indices_to_predictions.items()
    ]
    tmpfile = tempfile.NamedTemporaryFile("w+", dir=tmpdir.name, delete=False)
    tmpfile.write("\n".join(rows))
    tmpfile.seek(0)
    return tmpfile


def _create_mock_blob(
    name: str, fd: typing.IO[typing.Any] | None = None, exists: bool = True
):
    blob = mock.create_autospec(storage.Blob, instance=True)
    blob.name = name
    blob.open.return_value = fd
    blob.exists.return_value = exists
    return blob


def _create_mock_bucket(blobs: dict[str, mock.MagicMock]):
    bucket = mock.create_autospec(storage.Bucket, instance=True)
    bucket.blob.side_effect = lambda name: (
        blobs.get(name)
        if name in blobs
        else _create_mock_blob(name, fd=None, exists=False)
    )
    return bucket


@mock.patch.object(storage, "Client", autospec=True)
def test_merge_scenario_predictions(mock_storage_client, tmpdir, app) -> None:
    files = {
        "run/flood/model/nyc/scenario0/chunk0.csv": _create_chunk_file(
            {"h300": 0.00, "h301": 0.01}, tmpdir
        ),
        "run/flood/model/nyc/scenario0/chunk1.csv": _create_chunk_file(
            {"h310": 0.10, "h311": 0.11}, tmpdir
        ),
        # Chunk only exists in one scenario
        "run/flood/model/nyc/scenario0/chunk2.csv": _create_chunk_file(
            {"h320": 0.20, "h321": 0.21}, tmpdir
        ),
        # Chunk doesn't match file name pattern
        "run/flood/model/nyc/scenario0/ignore/chunk0.csv": _create_chunk_file(
            {"h300": 0.99, "h301": 9.99}, tmpdir
        ),
        "run/flood/model/nyc/scenario1/chunk0.csv": _create_chunk_file(
            {"h300": 1.00, "h301": 1.01}, tmpdir
        ),
        # Has extra h3 index
        "run/flood/model/nyc/scenario1/chunk1.csv": _create_chunk_file(
            {"h310": 1.10, "h311": 1.11, "h312": 1.12}, tmpdir
        ),
        # Scenario only exists for one chunk
        "run/flood/model/nyc/scenario2/chunk0.csv": _create_chunk_file(
            {"h300": 2.00, "h301": 2.01}, tmpdir
        ),
        "merged/run/nyc/flood/chunk0.csv": tempfile.NamedTemporaryFile(
            "w+", dir=tmpdir.name, delete=False
        ),
        "merged/run/nyc/flood/chunk1.csv": tempfile.NamedTemporaryFile(
            "w+", dir=tmpdir.name, delete=False
        ),
        "merged/run/nyc/flood/chunk2.csv": tempfile.NamedTemporaryFile(
            "w+", dir=tmpdir.name, delete=False
        ),
    }
    blobs = {name: _create_mock_blob(name, file) for name, file in files.items()}
    mock_storage_client().bucket.return_value = _create_mock_bucket(blobs)
    mock_storage_client().list_blobs.side_effect = lambda _, prefix: [
        blob for name, blob in blobs.items() if name.startswith(prefix)
    ]
    with app.test_request_context(
        query_string={
            "run_id": "run",
            "prediction_type": "flood",
            "model_id": "model",
            "study_area_name": "nyc",
        }
    ):
        result = main.merge_scenario_predictions(flask.request)
        assert result == ("Success", 200)

        expected_chunk0_contents = [
            "h3_index,scenario0,scenario1,scenario2\n",
            "h300,0.0,1.0,2.0\n",
            "h301,0.01,1.01,2.01\n",
        ]
        expected_chunk1_contents = [
            "h3_index,scenario0,scenario1,scenario2\n",
            "h310,0.1,1.1,\n",
            "h311,0.11,1.11,\n",
            "h312,,1.12,\n",
        ]
        expected_chunk2_contents = [
            "h3_index,scenario0,scenario1,scenario2\n",
            "h320,0.2,,\n",
            "h321,0.21,,\n",
        ]
        with open(files["merged/run/nyc/flood/chunk0.csv"].name) as fd:
            assert fd.readlines() == expected_chunk0_contents
        with open(files["merged/run/nyc/flood/chunk1.csv"].name) as fd:
            assert fd.readlines() == expected_chunk1_contents
        with open(files["merged/run/nyc/flood/chunk2.csv"].name) as fd:
            assert fd.readlines() == expected_chunk2_contents


@pytest.mark.parametrize(
    "arg_name", ["run_id", "prediction_type", "model_id", "study_area_name"]
)
def test_merge_scenario_predictions_missing_args(arg_name, app):
    query_string_args = {
        "run_id": "run",
        "prediction_type": "flood",
        "model_id": "model",
        "study_area_name": "nyc",
    }
    del query_string_args[arg_name]
    with app.test_request_context(query_string=query_string_args):
        result_msg, result_code = main.merge_scenario_predictions(flask.request)
        assert re.match(f"Bad request:.*{arg_name}.*", result_msg)
        assert result_code == 400
