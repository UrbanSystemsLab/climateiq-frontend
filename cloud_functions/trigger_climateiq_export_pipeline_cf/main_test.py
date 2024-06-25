import main
import pytest
from google.cloud import storage, pubsub_v1
from unittest.mock import patch, MagicMock, call
from cloudevents import http

def test_trigger_climateiq_export_pipeline_invalid_object_name():
    attributes = {
        "type": "google.cloud.storage.object.v1.finalized",
        "source": "source",
    }
    data = {
        "bucket": "climateiq-predictions",
        "name": "invalid_name",  # Invalid object name
    }
    event = http.CloudEvent(attributes, data)

    with pytest.raises(ValueError) as exc_info:
        main.trigger_climateiq_export_pipeline(event)

    assert "Invalid object name format. Expected format: '<id>/<prediction_type>/<model_id>/<study_area_name>/<scenario_id>/prediction.results-<file_number>-of-{number_of_files_generated}" in str(exc_info.value)

@patch.object(pubsub_v1, "PublisherClient", autospec=True)
@patch.object(storage, "Client", autospec=True)
def test_trigger_climateiq_export_pipeline_missing_prediction_files(mock_storage_client, mock_publisher):
    attributes = {
        "type": "google.cloud.storage.object.v1.finalized",
        "source": "source",
    }
    data = {
        "bucket": "climateiq-predictions",
        "name": "id1/flood/v1.0/manhattan/extreme/prediction.results-3-of-5",
    }
    event = http.CloudEvent(attributes, data)

    input_blobs = [
        storage.Blob(
            name="id1/flood/v1.0/manhattan/extreme/prediction.results-1-of-5",
            bucket=storage.Bucket(mock_storage_client, "climateiq-predcitions"),
        ),
        storage.Blob(
            name="id1/flood/v1.0/manhattan/extreme/prediction.results-3-of-5",
            bucket=storage.Bucket(mock_storage_client, "climateiq-predcitions"),
        ),
        storage.Blob(
            name="id1/flood/v1.0/manhattan/extreme/prediction.results-5-of-5",
            bucket=storage.Bucket(mock_storage_client, "climateiq-predcitions"),
        ),
    ]
    mock_storage_client().list_blobs.return_value = input_blobs

    main.trigger_climateiq_export_pipeline(event)

    mock_publisher().topic_path.assert_not_called()


@patch.object(pubsub_v1, "PublisherClient", autospec=True)
@patch.object(storage, "Client", autospec=True)
def test_trigger_climateiq_export_pipeline(mock_storage_client, mock_publisher):
    attributes = {
        "type": "google.cloud.storage.object.v1.finalized",
        "source": "source",
    }
    data = {
        "bucket": "climateiq-predictions",
        "name": "id1/flood/v1.0/manhattan/extreme/prediction.results-3-of-5",
    }
    event = http.CloudEvent(attributes, data)

    # Create 5 mock blobs with predictions for 2 chunks each
    def create_mock_blob(name, num):
        chunk_id = (num - 1) * 2 + 1
        predictions = "\n".join([
            f'{{"instance": {{"values": [{i}], "key": chunk{chunk_id + i}}}, "prediction": [[1, 2, 3], [4, 5, 6]]}}'
            for i in range(2)
        ])
        mock_blob = MagicMock(spec=storage.Blob)
        mock_blob.name = name
        mock_file = MagicMock()
        mock_file.__enter__.return_value = predictions.splitlines()
        mock_blob.open.return_value = mock_file
        return mock_blob
    input_blobs = [
        create_mock_blob(f"id1/flood/v1.0/manhattan/extreme/prediction.results-{i}-of-5", i) 
        for i in range(1, 6)
    ]
    mock_storage_client.return_value.list_blobs.return_value = input_blobs

    main.trigger_climateiq_export_pipeline(event)

    mock_publisher().publish.assert_has_calls(
    [
        call(
            "projects/climateiq/topics/climateiq-spatialize-and-export-predictions",
            data=b"id1/flood/v1.0/manhattan/extreme/chunk1",
            origin="trigger_climateiq_export_pipeline_cf",
        ),
        call().result(),
        call(
            "projects/climateiq/topics/climateiq-spatialize-and-export-predictions",
            data=b"id1/flood/v1.0/manhattan/extreme/chunk2",
            origin="trigger_climateiq_export_pipeline_cf",
        ),
        call().result(),
        call(
            "projects/climateiq/topics/climateiq-spatialize-and-export-predictions",
            data=b"id1/flood/v1.0/manhattan/extreme/chunk3",
            origin="trigger_climateiq_export_pipeline_cf",
        ),
        call().result(),
        call(
            "projects/climateiq/topics/climateiq-spatialize-and-export-predictions",
            data=b"id1/flood/v1.0/manhattan/extreme/chunk4",
            origin="trigger_climateiq_export_pipeline_cf",
        ),
        call().result(),
        call(
            "projects/climateiq/topics/climateiq-spatialize-and-export-predictions",
            data=b"id1/flood/v1.0/manhattan/extreme/chunk5",
            origin="trigger_climateiq_export_pipeline_cf",
        ),
        call().result(),
        call(
            "projects/climateiq/topics/climateiq-spatialize-and-export-predictions",
            data=b"id1/flood/v1.0/manhattan/extreme/chunk6",
            origin="trigger_climateiq_export_pipeline_cf",
        ),
        call().result(),
        call(
            "projects/climateiq/topics/climateiq-spatialize-and-export-predictions",
            data=b"id1/flood/v1.0/manhattan/extreme/chunk7",
            origin="trigger_climateiq_export_pipeline_cf",
        ),
        call().result(),
        call(
            "projects/climateiq/topics/climateiq-spatialize-and-export-predictions",
            data=b"id1/flood/v1.0/manhattan/extreme/chunk8",
            origin="trigger_climateiq_export_pipeline_cf",
        ),
        call().result(),
        call(
            "projects/climateiq/topics/climateiq-spatialize-and-export-predictions",
            data=b"id1/flood/v1.0/manhattan/extreme/chunk9",
            origin="trigger_climateiq_export_pipeline_cf",
        ),
        call().result(),
        call(
            "projects/climateiq/topics/climateiq-spatialize-and-export-predictions",
            data=b"id1/flood/v1.0/manhattan/extreme/chunk10",
            origin="trigger_climateiq_export_pipeline_cf",
        ),
        call().result(),
        call(
            "projects/climateiq/topics/climateiq-spatialize-and-export-predictions",
            data=b"id1/flood/v1.0/manhattan/extreme/chunk11",
            origin="trigger_climateiq_export_pipeline_cf",
        ),
        call().result(),
        call(
            "projects/climateiq/topics/climateiq-spatialize-and-export-predictions",
            data=b"id1/flood/v1.0/manhattan/extreme/chunk12",
            origin="trigger_climateiq_export_pipeline_cf",
        ),
        call().result(),
    ])