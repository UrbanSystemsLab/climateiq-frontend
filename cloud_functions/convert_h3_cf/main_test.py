import main
import pytest
import pandas as pd

from cloudevents.http import CloudEvent
from io import StringIO
from pandas.testing import assert_series_equal
from unittest import mock


@mock.patch.object(main.storage, "Client", autospec=True)
def test_convert_to_h3(mock_storage_client) -> None:
    attributes = {
        "type": "google.cloud.storage.object.v1.finalized",
        "source": "source",
    }
    data = {
        "bucket": "climateiq-predictions",
        "name": "prediction-type/model-id/study-area-name/scenario-id/chunk-id",
    }
    event = CloudEvent(attributes, data)

    input = pd.DataFrame(
        {
            "lat": [
                40.70663174,
                40.71484367,
                40.7104007,
                40.7030788,
                40.71584173,
                40.72138653,
            ],
            "lon": [
                -74.00989689,
                -74.00433053,
                -74.00246159,
                -74.00226216,
                -74.01739441,
                -74.01145063,
            ],
            "prediction": [4, 5, 6, 1, 2, 3],
        }
    )

    with mock_storage_client().bucket("").blob("").open() as mock_fd:
        mock_fd.read.return_value = input.to_json()

    expected_df = pd.Series(
        {
            "8a2a107288c7fff": 4.0,
            "8a2a10728967fff": 6.0,
            "8a2a10728b0ffff": 1.0,
            "8a2a10728d37fff": 2.0,
            "8a2a1072c287fff": 5.0,
            "8a2a1072c7a7fff": 3.0,
        }
    )

    with pytest.raises(NotImplementedError) as exc_info:
        main.convert_to_h3(event)

    assert_series_equal(
        pd.read_json(StringIO(str(exc_info.value)), typ="series"),
        expected_df,
        check_dtype=False,
    )
