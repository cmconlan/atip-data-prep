#!/bin/bash

# Assumes split_uk_osm.sh is done

# Don't enable this; better to best-effort as many places as possible
#set -e

cargo build --release
mkdir route-snappers

IFS=$'\n'
for x in uk_osm/out/*; do
	geojson=$(basename $x .osm).geojson
	cargo run --release $x uk_osm/$geojson
	mv *.bin route-snappers
done

# Put in S3
aws s3 sync --dry route-snappers s3://abstreet/route-snappers/