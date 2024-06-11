from cloudevents import http

import main


def test_merge_predictions() -> None:
    cloud_event = http.CloudEvent(
        {"type": "google.cloud.storage.object.v1.finalized", "source": "source"}, {}
    )
    assert main.merge_predictions(cloud_event) is None
