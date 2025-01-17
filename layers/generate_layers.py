#!/usr/bin/python3

import argparse
import json
import os
import shutil
import subprocess


# This tool generates multiple outputs:
# - schools.pmtiles
# - hospitals.pmtiles
# - mrn.pmtiles
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-i",
        "--osm_input",
        help="Path to england-latest.osm.pbf file",
        type=str,
        required=True,
    )
    args = parser.parse_args()

    # https://wiki.openstreetmap.org/wiki/Tag:amenity%3Dschool indicates
    # primary and secondary schools
    generatePolygonAmenity(args, "school", "schools")

    # Note https://wiki.openstreetmap.org/wiki/Tag:amenity%3Dhospital doesn't
    # cover all types of medical facility
    generatePolygonAmenity(args, "hospital", "hospitals")

    makeMRN()

    makeParliamentaryConstituencies()


# Extract `amenity={amenity}` polygons from OSM, and only keep a name attribute.
def generatePolygonAmenity(args, amenity, filename):
    # Remove files from any previous run
    try:
        os.remove(f"{filename}.osm.pbf")
        os.remove(f"{filename}.geojson")
        os.remove(f"{filename}.pmtiles")
    except:
        pass

    # First extract a .osm.pbf with all amenity={name} features
    # TODO Do we need nwr? We don't want points further on
    run(
        [
            "osmium",
            "tags-filter",
            args.osm_input,
            f"nwr/amenity={amenity}",
            "-o",
            f"{filename}.osm.pbf",
        ]
    )

    # Transform osm.pbf to GeoJSON, only keeping polygons. (Everything will be expressed as a MultiPolygon)
    run(
        [
            "osmium",
            "export",
            f"{filename}.osm.pbf",
            "--geometry-type=polygon",
            "-o",
            f"{filename}.geojson",
        ]
    )

    # Only keep one property
    remove_extra_properties(f"{filename}.geojson")

    # Convert to pmtiles. Default options are fine.
    run(["tippecanoe", f"{filename}.geojson", "-o", f"{filename}.pmtiles"])


def makeMRN():
    # Remove files from any previous run
    try:
        os.remove("Major_Road_Network_2018_Open_Roads.zip")
        shutil.rmtree("mrn")
        os.remove("mrn.pmtiles")
    except:
        pass

    # Get the shapefile
    run(
        [
            "wget",
            "https://maps.dft.gov.uk/major-road-network-shapefile/Major_Road_Network_2018_Open_Roads.zip",
        ]
    )
    run(["unzip", "Major_Road_Network_2018_Open_Roads.zip", "-d", "mrn"])

    # Convert to GeoJSON, projecting to WGS84
    run(
        [
            "ogr2ogr",
            "-f",
            "GeoJSON",
            "mrn/mrn.geojson",
            "-t_srs",
            "EPSG:4326",
            "mrn/Major_Road_Network_2018_Open_Roads.shp",
        ]
    )

    # Clean up the file
    path = "mrn/mrn.geojson"
    print(f"Cleaning up {path}")
    gj = {}
    with open(path) as f:
        gj = json.load(f)
        # Remove unnecessary attributes
        del gj["name"]
        del gj["crs"]
        for feature in gj["features"]:
            # Remove all properties except for "name1", and rename it
            props = {}
            name = feature["properties"].get("name1")
            if name:
                props["name"] = name
            feature["properties"] = props

            feature["geometry"]["coordinates"] = trim_precision(
                feature["geometry"]["coordinates"]
            )
    with open(path, "w") as f:
        f.write(json.dumps(gj))

    # Convert to pmtiles
    run(["tippecanoe", f"mrn/mrn.geojson", "-o", f"mrn.pmtiles"])


def makeParliamentaryConstituencies():
    # Remove files from any previous run
    try:
        os.remove("boundary_lines.zip")
        shutil.rmtree("boundary_lines")
        os.remove("parliamentary_constituencies.pmtiles")
    except:
        pass

    # Get the geopackage
    run(
        [
            "wget",
            # From https://osdatahub.os.uk/downloads/open/BoundaryLine
            "https://api.os.uk/downloads/v1/products/BoundaryLine/downloads?area=GB&format=GeoPackage&redirect",
            "-O",
            "boundary_lines.zip",
        ]
    )
    run(["unzip", "boundary_lines.zip", "-d", "boundary_lines"])

    # Convert to GeoJSON, projecting to WGS84. Only grab one layer.
    run(
        [
            "ogr2ogr",
            "-f",
            "GeoJSON",
            "boundary_lines/parliamentary_constituencies.geojson",
            "-t_srs",
            "EPSG:4326",
            "boundary_lines/Data/bdline_gb.gpkg",
            "-sql",
            # Just get a few fields from one layer, and filter for England
            "SELECT Name, Census_Code, geometry FROM westminster_const WHERE Census_Code LIKE 'E%'",
        ]
    )

    # Convert to pmtiles
    run(
        [
            "tippecanoe",
            f"boundary_lines/parliamentary_constituencies.geojson",
            "-o",
            f"parliamentary_constituencies.pmtiles",
        ]
    )


def run(args):
    print(">", " ".join(args))
    subprocess.run(args, check=True)


# For each GeoJSON feature, keep only the name attribute. Overwrites the given file.
def remove_extra_properties(path):
    print(f"Removing extra properties from {path}")
    gj = {}
    with open(path) as f:
        gj = json.load(f)
        for feature in gj["features"]:
            # Remove all properties except for "name"
            props = {}
            name = feature["properties"].get("name")
            if name:
                props["name"] = name
            feature["properties"] = props

    with open(path, "w") as f:
        f.write(json.dumps(gj))


# Round coordinates to 6 decimal places. Takes feature.geometry.coordinates,
# handling any type.
def trim_precision(data):
    if isinstance(data, list):
        return [trim_precision(x) for x in data]
    elif isinstance(data, float):
        return round(data, 6)
    else:
        raise Exception(f"Unexpected data within coordinates: {data}")


if __name__ == "__main__":
    main()
