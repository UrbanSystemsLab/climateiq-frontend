import trigger_climateiq_export_pipeline
from google.cloud import storage, pubsub_v1
from unittest.mock import patch, MagicMock, call


@patch.object(pubsub_v1, "PublisherClient", autospec=True)
@patch.object(storage, "Client", autospec=True)
def test_publish_messages(mock_storage_client, mock_publisher):
    mock_blobs = [
        storage.Blob(
            name="flood/v1.0/manhattan/extreme/chunk1",
            bucket=storage.Bucket(mock_storage_client, "climateiq-predcitions"),
        ),
        storage.Blob(
            name="flood/v1.0/manhattan/extreme/chunk2",
            bucket=storage.Bucket(mock_storage_client, "climateiq-predcitions"),
        ),
    ]
    mock_storage_client().list_blobs.return_value = mock_blobs

    mock_publisher().topic_path.return_value = (
        "projects/climateiq/topics/climateiq-spatialize-and-export-predictions"
    )
    mock_future = MagicMock()
    mock_future.result.return_value = "message_id"
    mock_publisher().publish.return_value = mock_future

    trigger_climateiq_export_pipeline.publish_messages("flood", "v1.0")

    mock_publisher().topic_path.assert_called_once_with(
        "climateiq", "climateiq-spatialize-and-export-predictions"
    )
    mock_storage_client().list_blobs.assert_called_once_with(
        "climateiq-predictions", prefix="flood/v1.0/"
    )
    mock_publisher().publish.assert_has_calls(
        [
            call(
                "projects/climateiq/topics/climateiq-spatialize-and-export-predictions",
                data=b"flood/v1.0/manhattan/extreme/chunk1",
                origin="trigger_climateiq_export_pipeline.py",
            ),
            call().result(),
            call(
                "projects/climateiq/topics/climateiq-spatialize-and-export-predictions",
                data=b"flood/v1.0/manhattan/extreme/chunk2",
                origin="trigger_climateiq_export_pipeline.py",
            ),
            call().result(),
        ]
    )
