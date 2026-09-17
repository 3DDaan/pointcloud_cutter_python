import os
import json
import laspy
import numpy as np
import geopandas as gpd
from shapely import box
from shapely.prepared import prep
from pyproj import CRS, Transformer

try:
    import pdal
    HAS_PDAL = True
except ImportError:
    HAS_PDAL = False


def clip_pointcloud_with_aoi_auto(
    input_laz: str,
    aoi_file: str,
    output_dir: str,
    chunk_size: int = 10_000_000,
    out_epsg: int = 3857,
):
    """
    Clips either a standard LAS/LAZ or COPC.LAZ file with an AOI.
    - COPC  -> handled via PDAL  (with AHN→EPSG:7415 auto-detect)
    - LAS/LAZ -> handled via laspy
    Output is reprojected to the provided EPSG (default 3857).
    """

    # --- Load AOI ---
    aoi = gpd.read_file(aoi_file)
    if aoi.crs is None:
        raise ValueError("AOI file has no CRS defined.")
    aoi_union = aoi.geometry.unary_union

    # --- Detect COPC ---
    is_copc = False
    with laspy.open(input_laz) as src:
        vlr_keys = [vlr.user_id.lower() for vlr in src.header.vlrs]
        if any("copc" in v for v in vlr_keys):
            is_copc = True

    basename = os.path.splitext(os.path.basename(input_laz))[0]
    output_path = os.path.join(output_dir, f"{basename}_clip.laz")
    os.makedirs(output_dir, exist_ok=True)
    out_srs = f"EPSG:{out_epsg}"

    # =====================================================
    # COPC HANDLING  →  PDAL
    # =====================================================
    if is_copc:
        if not HAS_PDAL:
            raise RuntimeError("PDAL is required for COPC files. Install with: conda install -c conda-forge pdal")

        print("Detected COPC file — running PDAL pipeline...")

        # Auto-detect AHN
        in_srs = None
        if "AHN" in os.path.basename(input_laz).upper():
            in_srs = "EPSG:7415"
            print("Detected AHN dataset → forcing input CRS EPSG:7415")
        else:
            print("No AHN detected → using internal CRS from COPC (if present)")

        # AOI must be in the same CRS as the reader (important!)
        if in_srs:
            aoi_crop = aoi.to_crs(in_srs)
        else:
            aoi_crop = aoi

        aoi_wkt = aoi_crop.geometry.unary_union.wkt

        # --- Define reader stage ---
        reader_stage = {
            "type": "readers.copc",
            "filename": input_laz,
            "threads": 1
        }

        # If AHN detected, tell PDAL what CRS the COPC uses
        if in_srs:
            reader_stage["spatialreference"] = in_srs

        # --- Define pipeline ---
        pipeline_def = {
            "pipeline": [
                reader_stage,
                {"type": "filters.crop", "polygon": aoi_wkt},
                {"type": "filters.reprojection", "out_srs": out_srs},
                {
                    "type": "writers.las",
                    "filename": output_path,
                    "minor_version": 4,
                    "compression": "laszip"
                }
            ]
        }

        pipeline = pdal.Pipeline(json.dumps(pipeline_def))
        try:
            count = pipeline.execute()
            log = pipeline.log
            print(f"PDAL processed {count} points.")
            if log:
                log_path = os.path.join(os.path.dirname(output_path), "pdal_log.txt")
                with open(log_path, "w", encoding="utf-8") as f:
                    f.write(log)
                print(f"Log written to: {log_path}")
            if count > 0:
                print(f"✓ COPC clipped & reprojected: {output_path}")
            else:
                print("⚠ No points found in AOI — check CRS or polygon extent.")
        except RuntimeError as e:
            print("PDAL pipeline failed:")
            print(e)
        return

    # =====================================================
    # STANDARD LAS/LAZ HANDLING  →  LASPY
    # =====================================================
    print("Standard LAS/LAZ detected — running laspy clip...")

    with laspy.open(input_laz) as src:
        pc_crs = src.header.parse_crs()
        if pc_crs is None:
            raise ValueError("Input point cloud has no CRS defined.")
        pc_crs = CRS.from_wkt(pc_crs.to_wkt())

    if aoi.crs != pc_crs:
        aoi = aoi.to_crs(pc_crs)
    aoi_union = aoi.geometry.unary_union
    minx, miny, maxx, maxy = aoi_union.bounds
    prep_aoi = prep(aoi_union)

    arrays = []
    with laspy.open(input_laz) as src:
        for chunk in src.chunk_iterator(chunk_size):
            x, y = chunk.x, chunk.y
            bbox_mask = (x >= minx) & (x <= maxx) & (y >= miny) & (y <= maxy)
            if not np.any(bbox_mask):
                continue
            x_sub, y_sub = x[bbox_mask], y[bbox_mask]
            precise_mask = np.array(
                [prep_aoi.contains(box(px, py, px, py)) for px, py in zip(x_sub, y_sub)]
            )
            mask = np.zeros_like(bbox_mask, dtype=bool)
            mask[bbox_mask] = precise_mask
            if np.any(mask):
                arrays.append(chunk.array[mask])

    if not arrays:
        print("No points found within AOI.")
        return

    merged_points = np.concatenate(arrays)

    with laspy.open(input_laz) as src:
        header = laspy.LasHeader(point_format=src.header.point_format, version=src.header.version)
        scales = src.header.scales
        offsets = src.header.offsets

    header.add_crs(CRS.from_epsg(out_epsg))
    las = laspy.LasData(header)
    las.points = laspy.ScaleAwarePointRecord(merged_points, header.point_format, scales, offsets)

    transformer = Transformer.from_crs(pc_crs, out_epsg, always_xy=True)
    las.x, las.y = transformer.transform(las.x, las.y)
    las.write(output_path)

    print(f"✓ LAS/LAZ clipped & reprojected: {output_path}")

# Example usage:
#%% Apply the clipping

if __name__ == "__main__":
    import pathlib

    # --- instellingen ---
    root_dir = pathlib.Path(r"PATH TO DIR")
    aoi_file = r"PATH TO AOI"
    out_epsg = 3857

    # doorloop alle submappen
    for laz_path in root_dir.rglob("*.[lL][aA][zZ]"):
        # --- skip Clipped output directories ---
        if "Clipped" in laz_path.parts:
            continue

        file_dir = laz_path.parent
        clip_dir = file_dir / "Clipped"
        clip_dir.mkdir(exist_ok=True)

        # maak outputpad met _clip achtervoegsel
        basename = laz_path.stem  # zelfde als os.path.splitext(laz_path.name)[0]
        output_path = clip_dir / f"{basename}_clip.laz"

        # --- check vóórdat iets verwerkt wordt ---
        if output_path.exists():
            print(f"⏩ Output bestaat al, overslaan: {output_path}")
            continue

        try:
            print("\n====================================")
            print(f"Processing: {laz_path}")
            print(f"Output → {output_path}")

            # run clipping pas nu
            clip_pointcloud_with_aoi_auto(str(laz_path), aoi_file, str(clip_dir), out_epsg=out_epsg)

        except KeyboardInterrupt:
            print("⛔ Handmatig gestopt.")
            break

        except Exception as e:
            print(f"⚠ Fout bij {laz_path.name}: {e}")


