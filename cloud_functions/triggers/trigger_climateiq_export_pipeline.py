from google.cloud import storage, pubsub_v1
import argparse

project_id = "climateiq"
topic_id = "climateiq-spatialize-and-export-predictions"
bucket_name = "climateiq-predictions"


def publish_messages(prediction_type, model_id):
    """Publishes Pub/Sub messages to the "climateiq-spatialize-and-export-predictions".

    For each chunk, initiates the export pipeline that spatializes, transforms and
    exports predictions for visualization on the ClimateIQ dashboard.

    Args:
        prediction_type: The hazard type to export predictions for.
        model_id: The model version to export predictions from.
    """
    # Pub/Sub setup
    publisher = pubsub_v1.PublisherClient()
    topic_path = publisher.topic_path(project_id, topic_id)

    # GCS setup
    storage_client = storage.Client()

    # Retrieve relevant chunk predictions
    blobs = storage_client.list_blobs(
        bucket_name, prefix=f"{prediction_type}/{model_id}/"
    )

    # Publish message for each chunk
    for blob in blobs:
        future = publisher.publish(
            topic_path,
            data=blob.name.encode("utf-8"),
            origin="trigger_climateiq_export_pipeline.py",
        )
        print(future.result())


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "prediction_type",
        help="The hazard type to export predictions for (e.g. flood, heat).",
    )
    parser.add_argument(
        "model_id", help="The model version to export predictions from."
    )
    args = parser.parse_args()

    publish_messages(args.prediction_type, args.model_id)
