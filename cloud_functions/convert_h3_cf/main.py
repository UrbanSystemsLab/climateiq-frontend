import functions_framework
import pandas as pd

from cloudevents.http import CloudEvent
from google.cloud import storage
from h3 import h3

H3_LEVEL = 10


@functions_framework.cloud_event
def convert_to_h3(cloud_event: CloudEvent) -> None:
    """This function is triggered when a new object is created or an existing
    object is overwritten by the climateiq_data_export_cf Cloud Function.

    Args:
        cloud_event: The CloudEvent representing the storage event.
    Raises:
        NotImplementedError: The result which should be stored elsewhere. This is:
            A pandas Series with h3 indices as keys and their corresponding predictions
            as the values.
    """
    data = cloud_event.data
    object_name = data["name"]
    bucket_name = data["bucket"]

    df = _read_json_to_df(bucket_name, object_name)
    df["h3"] = df.apply(_lat_lng_to_h3, axis=1)
    # TODO: Produce different aggregation(s) depending on prediction type.
    predictions = df.groupby(["h3"]).prediction.agg("mean")

    # TODO: Write output to storage.
    raise NotImplementedError(predictions.to_json())


def _read_json_to_df(bucket_name: str, object_name: str) -> pd.DataFrame:
    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(object_name)

    with blob.open() as fd:
        df = pd.read_json(fd)

    return df


def _lat_lng_to_h3(row, h3_level=H3_LEVEL):
    return h3.geo_to_h3(row["lat"], row["lon"], h3_level)
