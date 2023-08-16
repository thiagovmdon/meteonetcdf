# -*- coding: utf-8 -*-
"""
Created on Mon Aug 14 14:35:14 2023

@author: nascimth
"""

import numpy as np
from shapely.geometry import Polygon
import geopandas as gpd
from shapely.geometry import Point

def get_pixel_indices_and_coords(latitude, longitude, polygon):
    # Create a list to store pixel indices within the polygon
    pixel_indices = []
    pixel_coords = []

    # Iterate through latitude and longitude indices
    for lat_idx in range(len(latitude)):
        for lon_idx in range(len(longitude)):
            pixel_lat = latitude[lat_idx]
            pixel_lon = longitude[lon_idx]

            # Calculate the extent of the pixel
            pixel_extent = (
                pixel_lon - 0.125,  # Assuming pixel size is 0.25 degree
                pixel_lat - 0.125,  # Assuming pixel size is 0.25 degree
                pixel_lon + 0.125,  # Assuming pixel size is 0.25 degree
                pixel_lat + 0.125,  # Assuming pixel size is 0.25 degree
            )

            # Create a Polygon from the pixel extent
            pixel_polygon = Polygon([
                (pixel_extent[0], pixel_extent[1]),
                (pixel_extent[2], pixel_extent[1]),
                (pixel_extent[2], pixel_extent[3]),
                (pixel_extent[0], pixel_extent[3]),
            ])

            # Check if the pixel extent intersects with the polygon
            if pixel_polygon.intersects(polygon):
                pixel_indices.append((lat_idx, lon_idx))
                pixel_coords.append((pixel_lat, pixel_lon))

    # Convert the list of pixel indices to a NumPy array
    pixel_indices = np.array(pixel_indices)
    pixel_coords = np.array(pixel_coords)

    return pixel_indices, pixel_coords


#%%
chunk_size = 100  # Adjust this value based on your available memory

# Function to process a single catchment polygon
def process_catchment(catchmentname, shapefile_all, values, latitude, longitude, path_out):
    # Retrieve shapefile data and polygon for the given catchment
    shapefile = shapefile_all[shapefile_all.Code == catchmentname]
    polygon = shapefile.geometry.unary_union
    
    # Get pixel indices and coordinates within the catchment polygon
    pixel_indices, pixel_coords = get_pixel_indices_and_coords(latitude, longitude, polygon)
    
    # Check if there are no pixels within the catchment
    if len(pixel_indices) == 0:
        print(f"No pixels within catchment {catchmentname}. Skipping.")
        return

    # Create pixel polygons and calculate intersection areas
    pixel_points = [Point(lon, lat) for lat, lon in zip(latitude[pixel_indices[:, 0]], longitude[pixel_indices[:, 1]])]
    pixel_polygon = gpd.GeoSeries(pixel_points).buffer(0.125)
    intersection_areas = np.array(pixel_polygon.intersection(shapefile.geometry.unary_union).area)
    
    # Calculate weights for the catchment based on intersection areas
    weights_time_series = intersection_areas / intersection_areas.sum()

    # Define the size of the chunks for reading NetCDF data
    num_time_steps = values.shape[0]
    num_pixels = len(pixel_indices)
    
    # Initialize an array to store weighted time series data
    weighted_time_series = np.zeros((num_time_steps, num_pixels))

    for start_idx in range(0, num_time_steps, chunk_size):
        end_idx = min(start_idx + chunk_size, num_time_steps)
        chunk = values[start_idx:end_idx]
        
        # Extract chunk data for the selected pixels
        chunk_weighted = chunk[:, pixel_indices[:, 0], pixel_indices[:, 1]]
        weighted_time_series[start_idx:end_idx] = chunk_weighted
        
    # Replace -9999 values with NaN before calculating weighted sum
    weighted_time_series = np.where(weighted_time_series == -9999, np.nan, weighted_time_series)
    
    
    # Calculate the weighted sum considering only non-missing values and normalize weights
    valid_mask = ~np.isnan(weighted_time_series)
    valid_weighted_sum = np.nansum(weighted_time_series * weights_time_series, axis=1, keepdims=True)
    sum_valid_weights = np.nansum(weights_time_series * valid_mask, axis=1, keepdims=True)
    
    # Calculate final weighted sum, ensuring weights sum to 1
    weighted_sum = np.where(sum_valid_weights > 0, valid_weighted_sum / sum_valid_weights, np.nan)
    
    # We can also calculate the simple average:
    averaged_sum = np.nanmean(weighted_time_series, axis=1, keepdims=True)
    
    # Now we save our array to be saved:
    timeseries_array = np.hstack((weighted_sum, averaged_sum))
    
    # Prepare data for saving
    pixels_array = np.hstack((pixel_coords, intersection_areas.reshape((len(intersection_areas), 1)),
                              weights_time_series.reshape((len(weights_time_series), 1))))
    
    # Save pixel data and weighted sum data to CSV files
    np.savetxt(path_out + "pixels_" + catchmentname + ".csv", pixels_array, delimiter=',')
    np.savetxt(path_out + "rain_" + catchmentname + ".csv", timeseries_array, delimiter=',')