import json

from cloudevents import http
import functions_framework
import geopandas as gpd
from google.cloud import firestore
from google.cloud import storage
from h3 import h3
import pandas as pd
import pathlib
import numpy as np
from shapely import geometry

GLOBAL_CRS = "EPSG:4326"
H3_LEVEL = 13
STUDY_AREAS_ID = "study_areas"


# Triggered by the "object finalized" Cloud Storage event type.
@functions_framework.cloud_event
def export_model_predictions(cloud_event: http.CloudEvent) -> None:
    """This function is triggered when a new object is created or an existing
    object is overwritten in the "climateiq-predictions" storage bucket.

    Args:
        cloud_event: The CloudEvent representing the storage event. The name
        of the object should conform to the following pattern:
        "<prediction_type>/<model_id>/<study_area_name>/<scenario_id>/<chunk_id>"

    Raises:
        ValueError: If the object name format, study area metadata, chunk
        area metadata or predictions file format is invalid.
        NotImplementedError: The result which should be stored elsewhere. This is:
            a Series of h3 indices to the aggregated prediction.
    """
    data = cloud_event.data
    object_name = data["name"]
    bucket_name = data["bucket"]

    # Extract components from the object name.
    path = pathlib.PurePosixPath(object_name)
    if len(path.parts) != 5:
        raise ValueError("Invalid object name format. Expected 5 components.")

    prediction_type, model_id, study_area_name, scenario_id, chunk_id = path.parts

    predictions = _read_chunk_predictions(bucket_name, object_name)
    study_area_metadata = _get_study_area_metadata(study_area_name)
    chunk_metadata = _get_chunk_metadata(study_area_metadata, chunk_id)

    spatialized_predictions = _build_spatialized_model_predictions(
        study_area_metadata, chunk_metadata, predictions
    )

    h3_predictions = _calculate_h3_indexes(
        study_area_metadata, chunk_metadata, spatialized_predictions
    )

    # Set the error message to the Series' json string for testing
    # purposes. In the actual implementation, the Series should be stored somewhere.
    raise NotImplementedError(h3_predictions.to_json())


# TODO: Modify this logic once CNN output schema is confirmed. Also update to
# account for errors and special values.
def _read_chunk_predictions(bucket_name: str, object_name: str) -> np.ndarray:
    """Reads model predictions for a given chunk from GCS and outputs
    these predictions in a 2D array.

    Args:
        bucket_name (str): The name of the GCS bucket containing the chunk
        object.
        object_name (str): The name of the chunk object to read.

    Returns:
        np.ndarray: A 2D array containing the model predictions for the chunk.

    Raises:
        ValueError: If the predictions file format is invalid.
    """
    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(object_name)

    with blob.open() as fd:
        fd_iter = iter(fd)
        line = next(fd_iter, None)
        # Vertex AI will output one predictions file per chunk so the file is
        # expected to contain only one prediction.
        if line is None:
            raise ValueError("Predictions file is missing predictions.")

        prediction = json.loads(line)["prediction"]

        if next(fd_iter, None) is not None:
            raise ValueError("Predictions file has too many predictions.")

    return np.array(prediction)


def _get_study_area_metadata(study_area_name: str) -> dict:
    """Retrieves metadata for a given study area from Firestore.

    Args:
        study_area_name: The name of the study area to retrieve metadata for.

    Returns:
        A dictionary containing metadata for the study area.

    Raises:
        ValueError: If the study area does not exist or its metadata is
        missing required fields.
    """
    # TODO: Consider refactoring this to use library from climateiq-cnn repo.
    db = firestore.Client()

    study_area_ref = db.collection(STUDY_AREAS_ID).document(study_area_name)
    study_area_doc = study_area_ref.get()

    if not study_area_doc.exists:
        raise ValueError(f'Study area "{study_area_name}" does not exist')

    study_area_metadata = study_area_doc.to_dict()
    if (
        study_area_metadata.get("cell_size") is None
        or study_area_metadata.get("crs") is None
        or study_area_metadata.get("chunks") is None
    ):
        raise ValueError(
            f'Study area "{study_area_name}" is missing one or more required '
            "fields: cell_size, crs, chunks"
        )

    return study_area_metadata


def _get_chunk_metadata(study_area_metadata: dict, chunk_id: str) -> dict:
    """Retrieves metadata for a specific chunk within a study area.

    Args:
        study_area_metadata: A dictionary containing metadata for the
        study area.
        chunk_id: The unique identifier of the chunk to retrieve metadata for.

    Returns:
        A dictionary containing metadata for the chunk.

    Raises:
        ValueError: If the specified chunk does not exist or its metadata is
        missing required fields.
    """
    chunks = study_area_metadata["chunks"]
    chunk_metadata = chunks.get(chunk_id)

    if chunk_metadata is None:
        raise ValueError(f'Chunk "{chunk_id}" does not exist')

    if (
        chunk_metadata.get("row_count") is None
        or chunk_metadata.get("col_count") is None
        or chunk_metadata.get("x_ll_corner") is None
        or chunk_metadata.get("y_ll_corner") is None
    ):
        raise ValueError(
            f'Chunk "{chunk_id}" is missing one or more required fields: '
            "row_count, col_count, x_ll_corner, y_ll_corner"
        )

    return chunk_metadata


def _build_spatialized_model_predictions(
    study_area_metadata: dict, chunk_metadata: dict, predictions: np.ndarray
) -> pd.DataFrame:
    """Builds a DataFrame containing the lat/lon coordinates of each cell's
    center point.

    Args:
        study_area_metadata: A dictionary containing metadata for the study
        area.
        chunk_metadata: A dictionary containing metadata for the chunk.
        predictions: A 2D array containing the model predictions for the chunk.

    Returns:
        A DataFrame containing the lat/lon coordinates of cell centroids in a
        single chunk along with associated predictions, representing a
        subset of the full study area results.
    """
    rows = np.arange(chunk_metadata["row_count"])
    cols = np.arange(chunk_metadata["col_count"])

    # Calculate cell's center point in the source CRS.
    x_centers = (
        chunk_metadata["x_ll_corner"] + (cols + 0.5) * study_area_metadata["cell_size"]
    )
    y_centers = (
        chunk_metadata["y_ll_corner"] + (rows + 0.5) * study_area_metadata["cell_size"]
    )
    x_grid, y_grid = np.meshgrid(x_centers, y_centers)

    # Convert 2D meshgrids to 1D arrays.
    x_coords = x_grid.flatten()
    y_coords = y_grid.flatten()

    # Convert coordinates from the source CRS to the global CRS (lat/lon).
    gdf_src_crs = gpd.GeoDataFrame(
        geometry=gpd.points_from_xy(x_coords, y_coords),
        crs=study_area_metadata["crs"],
    )
    gdf_global_crs = gdf_src_crs.to_crs(GLOBAL_CRS)

    # Reverse prediction rows to align with generated coordinates.
    aligned_predictions = np.flipud(predictions).flatten()

    return pd.DataFrame(
        {
            "lat": gdf_global_crs.geometry.y,
            "lon": gdf_global_crs.geometry.x,
            "prediction": aligned_predictions,
        }
    )


def _add_h3_index_details(cell: pd.Series) -> pd.Series:
    """Projects the cell centroid to a H3 index.

    Args:
        cell: A cell row containing the lat and lon of the cell centroid.

    Returns:
        A Series containing H3 information for the projected cell centroid.

    """
    h3_index = h3.geo_to_h3(cell["lat"], cell["lon"], H3_LEVEL)
    centroid_lat, centroid_lon = h3.h3_to_geo(h3_index)
    boundary_xy = h3.h3_to_geo_boundary(h3_index, True)
    return pd.Series(
        {
            "h3_index": h3_index,
            "h3_centroid_lat": centroid_lat,
            "h3_centroid_lon": centroid_lon,
            "h3_boundary": geometry.Polygon(boundary_xy),
        }
    )


def _get_chunk_boundary(study_area_metadata: dict, chunk_metadata: dict):
    """Calculates the boundary points of the chunk.

    Args:
        study_area_metadata: A dictionary containing metadata for the study
        area.
        chunk_metadata: A dictionary containing metadata for the chunk.

    Returns:
        A shapely.Polygon representing the chunk.

    """
    min_x = chunk_metadata["x_ll_corner"]
    min_y = chunk_metadata["y_ll_corner"]
    max_x = min_x + chunk_metadata["col_count"] * study_area_metadata["cell_size"]
    max_y = min_y + chunk_metadata["row_count"] * study_area_metadata["cell_size"]

    boundary_points = [
        (min_x, min_y),
        (max_x, min_y),
        (max_x, max_y),
        (min_x, max_y),
        (min_x, min_y),
    ]

    gdf_src_crs = gpd.GeoDataFrame(
        geometry=[geometry.Polygon(boundary_points)],
        crs=study_area_metadata["crs"],
    )
    gdf_global_crs = gdf_src_crs.to_crs(GLOBAL_CRS)
    return gdf_global_crs.geometry[0]


def _calculate_h3_indexes(
    study_area_metadata: dict,
    chunk_metadata: dict,
    spatialized_predictions: pd.DataFrame,
) -> pd.Series:
    """Projects cell centroids to H3 indexes.

    Filters out cells that have projected H3 centroids outside of the current
    chunk and de-dupes duplicate H3 projections by using the average prediction
    value from overlapping cells.

    Args:
        study_area_metadata: A dictionary containing metadata for the study
        area.
        chunk_metadata: A dictionary containing metadata for the chunk.
        spatialized_predictions: A DataFrame containing the lat/lon coordinates of cell
        centroids in a single chunk along with associated predictions

    Returns:
        A Series containing H3 indexes in a single chunk along with associated
        predictions, representing a subset of the full study area results.

    """
    # Calculate H3 information for each cell.
    spatialized_predictions[
        ["h3_index", "h3_centroid_lat", "h3_centroid_lon", "h3_boundary"]
    ] = spatialized_predictions.apply(_add_h3_index_details, axis=1)

    # Filter out any cells where the projected H3 centroid falls outside of the
    # chunk boundary.
    chunk_boundary = _get_chunk_boundary(study_area_metadata, chunk_metadata)
    spatialized_predictions = spatialized_predictions[
        spatialized_predictions.apply(
            lambda cell: chunk_boundary.contains(
                geometry.Point(cell["h3_centroid_lon"], cell["h3_centroid_lat"])
            ),
            axis=1,
        )
    ]

    # TODO: Add logic for fetching predictions from neighboring chunks for boundary
    # cells.
    spatialized_predictions = spatialized_predictions.groupby(
        ["h3_index"]
    ).prediction.agg("mean")
    return spatialized_predictions
