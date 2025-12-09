# Pointcloud AOI Cutter (Python)

Utility script to clip LAS/LAZ or COPC LAZ point clouds to an Area of Interest (AOI) and reproject the result to Web Mercator (EPSG:3857). COPC files are processed via PDAL; standard LAS/LAZ files are processed via laspy in chunks to stay memory-friendly.

## Features
- Clips both standard LAS/LAZ and COPC LAZ files to a provided AOI polygon/footprint.
- Auto-detects AHN COPC files (filename contains `AHN`) and forces input CRS to EPSG:7415; otherwise uses the COPC’s internal CRS.
- Reprojects all outputs to EPSG:3857 and writes LAS 1.4 with LASzip compression.
- Chunked reading for large LAS/LAZ files to keep memory usage reasonable.
- Optional PDAL log written next to the output when COPC processing runs.

## Requirements
- Python 3.10+ recommended.
- Core Python deps: `laspy`, `numpy`, `geopandas`, `shapely`, `pyproj`.
- COPC support: `pdal` (installable via conda-forge; pip wheels are not always available).
- Data prerequisites: AOI file (GeoPackage/Shapefile/etc.) with a defined CRS; input point clouds with a defined CRS.

Example install (conda):
```bash
conda create -n pointcloud-cutter python=3.11
conda activate pointcloud-cutter
conda install -c conda-forge laspy numpy geopandas shapely pyproj pdal
```
For pip (non-COPC use):
```bash
pip install laspy numpy geopandas shapely pyproj
# PDAL is optional but required for COPC: install via conda if needed.
```

## Usage

### 1) Direct function call
```python
from src.Pointcloud_AOI_cutter import clip_pointcloud_with_aoi_auto

clip_pointcloud_with_aoi_auto(
    input_laz="path/to/input.laz",      # LAS/LAZ or COPC LAZ
    aoi_file="path/to/aoi.gpkg",        # AOI polygon with CRS
    output_dir="path/to/output/dir",    # created if missing
    chunk_size=10_000_000               # only used for standard LAS/LAZ
)
```

### 2) Batch processing via the included main block
Edit the paths in `src/Pointcloud_AOI_cutter.py` (near the bottom) and run:
```bash
python src/Pointcloud_AOI_cutter.py
```
What the main block does:
- Recursively scans `root_dir` for `*.laz` files.
- Skips any directories named `Clipped`.
- Writes clipped outputs to a sibling `Clipped/` folder, appending `_clip.laz`.
- Skips files that already have an output present.

## Notes and tips
- The AOI CRS must be defined; the script will error if it is missing.
- For standard LAS/LAZ, the AOI is reprojected to the point cloud CRS before clipping, then the output is reprojected to EPSG:3857.
- For COPC, the AOI is reprojected to the reader CRS (EPSG:7415 for AHN, otherwise the COPC’s internal CRS) before clipping.
- If you see “No points found within AOI,” double-check AOI extent and CRS alignment.
- When PDAL runs, a `pdal_log.txt` is written next to the output for debugging.

## Project layout
- `src/Pointcloud_AOI_cutter.py` — clipping logic and batch runner.
- `LICENSE` — GPL-3.0-only license text.

## License
GPL-3.0; see `LICENSE`.
