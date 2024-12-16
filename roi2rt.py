import os, shutil, argparse
from glob import glob
import os.path as osp
from warnings import warn
import os, sys, json, shutil, pathlib, pydicom
import numpy as np
import cv2
from vlkit import normalize
from rt_utils import RTStructBuilder
from tqdm import tqdm
from pydicom import dcmread


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

class dotdict(dict):
    """dot.notation access to dictionary attributes"""
    __getattr__ = dict.get
    __setattr__ = dict.__setitem__
    __delattr__ = dict.__delitem__


def read_dicom_info(input):
    if isinstance(input, str):
        dicoms = sorted(glob(f"{input}/**/*.dcm", recursive = True))
    else:
        assert isinstance(input, list)
        dicoms = input
    results = []

    for d in tqdm(dicoms):
        try:
            ds = pydicom.dcmread(d)
        except:
            warn(f"{d} is not a valid dicom file")
            continue
        InstanceNumber = int(ds.InstanceNumber) if hasattr(ds, 'InstanceNumber') else None
        ds = dict(
            fullpath=d,
            SeriesDescription=ds.SeriesDescription if hasattr(ds, "SeriesDescription") else "",
            SeriesInstanceUID=ds.SeriesInstanceUID,
            SOPInstanceUID=ds.SOPInstanceUID,
            StudyInstanceUID=ds.StudyInstanceUID,
            InstanceNumber=InstanceNumber,
            SliceLocation=float(ds.SliceLocation) if hasattr(ds, 'SliceLocation') else None,
            ImagePositionPatient=np.array(ds.ImagePositionPatient) if hasattr(ds, 'ImagePositionPatient') else None,
            is_osirix_sr=hasattr(ds, 'EncapsulatedDocument'))
        results.append(dotdict(ds))
    return results


def group_into_series(dicoms):
    """
    group dicoms into different series according to their
    `SeriesInstanceUID`
    """
    series = dict()
    for ds in dicoms:
        if ds.SeriesInstanceUID not in series:
            series[ds.SeriesInstanceUID] = [ds]
        else:
            series[ds.SeriesInstanceUID].append(ds)
    return series


def get_common_prefix(paths):
    shortest = 0
    # find the shallowest file path
    for idx, f in enumerate(paths):
        if len(paths[shortest].split(osp.sep)) <len(f.split(osp.sep)):
            shortest = idx
    shortest = paths[shortest].split(osp.sep)
    for i in range(len(shortest), 0, -1):
        path = osp.sep.join(shortest[:i])
        if all([pathlib.PurePath(p).is_relative_to(path) for p in paths]):
            return path


def group_into_studies(dicoms):
    """
    Group dicoms into studies according to StudyInstanceUID
    """
    studies = dict()
    for dcm in dicoms:
        if not hasattr(dcm, "StudyInstanceUID"):
            warn(f"{dcm.fullpath} does not have 'StudyInstanceUID' attribute")
            continue
        if dcm.StudyInstanceUID in studies:
            studies[dcm.StudyInstanceUID].append(dcm)
        else:
            studies[dcm.StudyInstanceUID] = [dcm]
    return studies


def build_SOPInstanceUID_lookup_table(dicoms):
    """
    build look-up-table from SOPInstanceUID to dicom
    """
    SOPInstanceUID_lookup_table = dict()
    for ds in dicoms:
        SOPInstanceUID_lookup_table[ds.SOPInstanceUID] = ds
    return SOPInstanceUID_lookup_table


def process(data_dir):
    print(f"Searching dicom files in {data_dir}, this may take a while.")
    dicoms = glob(f"{data_dir}/**/*.dcm", recursive=True)
    if len(dicoms) == 0:
        raise RuntimeError(f"no dicom file found in {data_dir}")
    else:
        print(f"Found {len(dicoms)} dicom files, gathering their meta data.")
    dicom_info = read_dicom_info(dicoms)
    studies = group_into_studies(dicom_info)

    # find all json ROIs
    roi_jsons = glob(f"{data_dir}/**/*.json", recursive=True)
    if len(roi_jsons) == 0:
        warn(f"No json found in {data_dir}.")
        return
    print(f"Found {len(roi_jsons)} jsons in {data_dir}.")

    for study_idx, (study_instance_uid, study_dicom_info) in enumerate(studies.items()):
        dicom_paths = [dcm.fullpath for dcm in study_dicom_info]
        study_prefix = get_common_prefix(dicom_paths)
        print(f"Processing study {study_idx}: {study_prefix}.")

        SOPInstanceUID_lookup_table = build_SOPInstanceUID_lookup_table(study_dicom_info)
        series_instance_uid2series = group_into_series(dicom_info)

        for js in roi_jsons:
            roi_data = json.load(open(js, 'r'))
            if "Images" not in roi_data or len(roi_data["Images"]) == 0:
                warn(f"No ROI found in {js}.")
                continue

            if study_instance_uid != roi_data["Images"][0]["ROIs"][0]["StudyInstanceUID"]:
                print(f"json {js} does not correspond to study {study_prefix}.")
                continue

            SeriesInstanceUID = roi_data["Images"][0]["ROIs"][0]["SeriesInstanceUID"]

            h, w = roi_data["Images"][0]["ImageHeight"], roi_data["Images"][0]["ImageWidth"]
            
            
            tmp_series_dir = osp.join("/tmp", "roi2rtstruct", "series", SeriesInstanceUID)
            os.makedirs(tmp_series_dir, exist_ok=True)

            series = sorted(series_instance_uid2series[SeriesInstanceUID], key=lambda x:x['fullpath'])
            series_prefix = get_common_prefix([s.fullpath for s in series])

            if args.save_to is not None:
                for s in series:
                    relpath = osp.relpath(s.fullpath, start=data_dir)
                    save_path = osp.join(args.save_to, relpath)
                    os.makedirs(osp.dirname(save_path), exist_ok=True)
                    shutil.copy(s.fullpath, save_path)

            for s in series:
                target = osp.join(tmp_series_dir, osp.basename(s.fullpath))
                os.makedirs(osp.dirname(target), exist_ok=True)
                shutil.copy(s.fullpath, target)

            named3dmask = dict()

            for img_idx, image in enumerate(roi_data['Images']):
                assert h == image["ImageHeight"] and w == image["ImageWidth"]

                rois = image['ROIs']
                if len(rois) == 0:
                    warn(f"No ROI found in image #{img_idx} of {js}.")
                    continue

                assert SeriesInstanceUID == rois[0]["SeriesInstanceUID"]

                rtstruct = RTStructBuilder.create_new(dicom_series_path=tmp_series_dir)
                for roi_idx, roi in enumerate(rois):
                    SOPInstanceUID = roi["SOPInstanceUID"]
                    slice = SOPInstanceUID_lookup_table[roi["SOPInstanceUID"]]

                    if series[-1].ImagePositionPatient[2] < series[0].ImagePositionPatient[2]:
                        slice_idx = len(series) - slice.InstanceNumber
                    else:
                        slice_idx = slice.InstanceNumber

                    assert roi["SeriesInstanceUID"] == SeriesInstanceUID

                    roi_name =  roi["Name"]                    
                    points = np.array([eval(point) for point in roi['Point_px']])

                    if roi_name not in named3dmask:
                        named3dmask[roi_name] = np.zeros((h, w, len(series)), dtype=bool)

                    mask1 = np.zeros((h, w), dtype=np.uint8)
                    cv2.fillPoly(mask1, [points.astype(np.int32)], color=1)
                    named3dmask[roi_name][:, :, slice_idx] = mask1

                    if args.save_to is not None:
                        relpath = osp.relpath(slice.fullpath, start=data_dir)
                        save_path = osp.join(args.save_to, relpath)

                    if True and args.save_to is not None:
                        # visualization
                        img = normalize(dcmread(slice.fullpath).pixel_array, 0, 1)
                        img = np.stack([img] * 3, axis=-1)
                        red = np.zeros_like(img)
                        red[:, :, -1] = 1
                        alpha = 0.3
                        overlay = red * mask1[:, :, None] * alpha + img * (1 - alpha)
                        overlay = normalize(overlay, 0, 255).astype(np.uint8)
                        
                        cv2.imwrite(f"{save_path}.{roi_name}.overlay.jpg", overlay)
                        #
                        np.save(f"{save_path}.{roi_name}.npy", mask1)
                        cv2.imwrite(f"{save_path}.{roi_name}_mask.png", mask1 * 255)
                    #
                    # print(f"Series {series_prefix}: ROI {roi_name} on slice #{slice_idx+1}.")

            for name, mask in named3dmask.items():
                rtstruct.add_roi(mask=mask, name="kai_"+name, approximate_contours=False)
            rtstruct.save(osp.join(study_prefix, SeriesInstanceUID+"_rtstruct.dcm"))


if __name__ == "__main__":
    args = parse_args()
    if not osp.isdir(args.dicom):
        raise RuntimeError(f'{args.dicom} is not a directory')
    if args.dicom == '/':
        warn("You are searching dicoms in the root directory, this might be EXTREMELY time-consuming. Consider providing a more specific sub-directory.")
    process(args.dicom)
