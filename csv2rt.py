import os, shutil, argparse
from glob import glob
import os.path as osp
from warnings import warn
import os, sys, json, shutil, pathlib, pydicom, hashlib
import numpy as np
import cv2
from vlkit import normalize
from rt_utils import RTStructBuilder
from pydicom import dcmread
from parse_roi import parse_csv
from vlkit.dicom import (
    group_dicoms_into_series,
    group_dicoms_into_studies,
    build_sop_instance_uid_lookup_table
)
from dicom_utils import read_dicom_info
from vlkit import str2color


def parse_args():
    parser = argparse.ArgumentParser(
        prog="rtconvert",
        usage="rtconvert path/to/dicoms/",
        description="""Convert annotations to dicom-rt structure set.
        It will search all suported annotations (currently support OsirixSR)
        and corresponding dicom files, and convert annotations into dicom-rt structure.
        """
        )
    parser.add_argument('dicom')
    parser.add_argument('--save-to', type=str, default=None)
    
    args =  parser.parse_args()
    return args

def process(data_dir):
    print(f"Searching dicom files in {data_dir}, this may take a while.")
    dicoms = glob(f"{data_dir}/**/*.dcm", recursive=True)
    if len(dicoms) == 0:
        raise RuntimeError(f"no dicom file found in {data_dir}")
    else:
        print(f"Found {len(dicoms)} dicom files, gathering their meta data.")
    dicom_info = read_dicom_info(dicoms)
    studies = group_dicoms_into_studies(dicom_info)

    # find all json ROIs
    csv_files = glob(f"{data_dir}/**/*.csv", recursive=True)
    if len(csv_files) == 0:
        warn(f"No csv found in {data_dir}.")
        return
    print(f"Found {len(csv_files)} jsons in {data_dir}.")
    SeriesInstanceUID2csv = dict()
    for csv in csv_files:
        rois = parse_csv(csv)
        assert len(rois) > 0, f"No ROI found in {csv}."
        SeriesInstanceUID2csv[
            rois[0]["SeriesInstanceUID"]
        ] = dict(csv=csv, rois=rois)

    for study_idx, (study_instance_uid, study_dicom_info) in enumerate(studies.items()):
        dicom_paths = [dcm.fullpath for dcm in study_dicom_info]
        study_prefix = osp.commonpath(dicom_paths)
        print(f"Processing study {study_idx}: {study_prefix}.")

        SOPInstanceUID_lookup_table = build_sop_instance_uid_lookup_table(study_dicom_info)
        series_instance_uid2series = group_dicoms_into_series(study_dicom_info, remove_duplicates=True)

        for series_idx, (SeriesInstanceUID, series) in enumerate(series_instance_uid2series.items()):
            unique_sop_instance_uids = set([s.SOPInstanceUID for s in series])
            series_perfix = osp.commonpath([s.fullpath for s in series])
            if len(unique_sop_instance_uids) != len(series):
                raise RuntimeError(f"Duplicate SOPInstanceUID found in series {series_perfix}.")
            
            if SeriesInstanceUID not in SeriesInstanceUID2csv:
                warn(f"No ROIs found for {series_perfix} id={SeriesInstanceUID}.")
                continue
            csv = SeriesInstanceUID2csv[SeriesInstanceUID]
            series = sorted(series, key=lambda x:x.fullpath)

            print(f"Series {series_perfix} ({len(series)}  dicoms) matched with {csv['csv']}.")

            tmp_series_dir = osp.join(args.save_to, osp.relpath(series_perfix, data_dir))
            try:
                # copy series to target
                os.makedirs(tmp_series_dir, exist_ok=True)
                for s in series:
                    shutil.copy(s.fullpath, tmp_series_dir)
                #
                h, w = dcmread(series[0].fullpath).pixel_array.shape
                for s in series:
                    assert dcmread(s.fullpath).pixel_array.shape == (h, w), f"Bad dimension: {s.fullpath}."

                named3dmask = dict()
                roi_names = set([roi["RoiName"] for roi in rois])
                for name in roi_names:
                    named3dmask[name] = np.zeros((h, w, len(series)), dtype=bool)

                rtstruct = RTStructBuilder.create_new(dicom_series_path=tmp_series_dir)

                for roi_name in roi_names:
                    for roi in rois:
                        if roi["RoiName"] == roi_name:
                            # sanity check
                            ImageNo = int(roi["ImageNo"])
                            s = series[ImageNo]
                            assert roi["SOPInstanceUID"] == s.SOPInstanceUID, f"{roi['SOPInstanceUID']} v.s. {s.SOPInstanceUID}."
                            # generate masks
                            mask1 = named3dmask[roi_name][:, :, ImageNo].copy().astype(np.uint8)
                            cv2.fillPoly(mask1, [roi["points_px"].astype(np.int32)], color=1)
                            named3dmask[roi_name][:, :, int(roi["ImageNo"])] = mask1.astype(bool)

                for i, s in enumerate(series):
                    relpath = osp.relpath(s.fullpath, start=data_dir)
                    save_to = osp.join(args.save_to, relpath)
                    os.makedirs(osp.dirname(save_to), exist_ok=True)
                    shutil.copy(s.fullpath, save_to)
                    mask1 = named3dmask[roi_name][:, :, i]
                    if mask1.sum() > 0:
                        np.save(f"{save_to}.{roi_name}.npy", mask1)
                        cv2.imwrite(f"{save_to}.{roi_name}_mask.png", mask1 * 255)
                        img = normalize(dcmread(s.fullpath).pixel_array, 0, 1)
                        img = np.stack([img] * 3, axis=-1)
                        color = np.ones((h, w, 3)) * np.array(str2color(roi_name))
                        alpha = 0.3
                        overlay = color * mask1[:, :, None] * alpha + img * (1 - alpha)
                        overlay = normalize(overlay, 0, 255).astype(np.uint8)
                        cv2.imwrite(f"{save_to}.{roi_name}.overlay.jpg", overlay)
                        # print(f"Writing visualization to {save_to}. [{i+1}/{len(series)}].")
                rtstruct.add_roi(mask=named3dmask[roi_name], name=roi_name)
                rtstruct.save(osp.join(study_prefix, SeriesInstanceUID+"_rtstruct.dcm"))
            except Exception as e:
                warn(f"Failed to process {series_perfix}. {e}")
                shutil.rmtree(tmp_series_dir)


if __name__ == "__main__":
    args = parse_args()
    if not osp.isdir(args.dicom):
        raise RuntimeError(f'{args.dicom} is not a directory')
    if args.dicom == '/':
        warn("You are searching dicoms in the root directory, this might be EXTREMELY time-consuming. Consider providing a more specific sub-directory.")
    process(args.dicom)
