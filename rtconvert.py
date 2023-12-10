import os, shutil, argparse, time
from glob import glob
import os.path as osp
from warnings import warn
import itertools, os, sys
RT_UTILS=osp.join(osp.dirname(__file__), "rt-utils")
sys.path.insert(0, RT_UTILS)
from rt_utils import RTStructBuilder
from rt_utils.utils import Polygon2D
from osirix_parser import OsirixSRParser
from tqdm import tqdm
from pydicom import dcmread

from dicom_utils import (
    read_dicom_info,
    group_study_into_series,
    find_osirix_sr,
    osirix_get_reference_uid,
    group_into_studies,
    get_common_prefix,
    build_SOPInstanceUID_lookup_table)


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
    return parser.parse_args()


def process(data_dir):
    osirix_parser = OsirixSRParser()
    print(f"Searching dicom files in {data_dir}, this may take a while.")
    dicoms = glob(f"{data_dir}/**/*.dcm", recursive=True)
    if len(dicoms) == 0:
        raise RuntimeError(f"no dicom file found in {data_dir}")
    else:
        print(f"Found {len(dicoms)} dicom files, gathering their meta data.")
    dicom_info = read_dicom_info(dicoms)
    studies = group_into_studies(dicom_info)
    for study_instance_uid, dicoms in studies.items():
        dicom_paths = [dcm.fullpath for dcm in dicom_info]
        study_prefix = get_common_prefix(dicom_paths)
        SOPInstanceUID_lookup_table = build_SOPInstanceUID_lookup_table(dicom_info)
        series_instance_uid2series = group_study_into_series(dicom_info)
        # find out all Osirix SR files
        osirix_sr = find_osirix_sr(dicom_info)

        # eliminate all OsirixSR files without an associated dicom
        associated = [osirix_get_reference_uid(osx) in SOPInstanceUID_lookup_table for osx in osirix_sr]
        if not all(associated):
            ignored = [osp.basename(osx.fullpath) for osx, ass in zip(osirix_sr, associated) if ass is False]
            ignored_str = ", ".join(ignored)
            warn(f"study \"{study_prefix}\" OsirixSR \"{ignored_str}\" ignored due to unable to find associated dicom")
            osirix_sr = list(itertools.compress(osirix_sr, associated))

        # assign Osirix SR to series
        # since the Osirix SR ROIs might be annotated on difference series
        series_instance_uid2osirixsr = dict()
        for osx in osirix_sr:
            series_instance_uid = SOPInstanceUID_lookup_table[osirix_get_reference_uid(osx)].SeriesInstanceUID
            if series_instance_uid in series_instance_uid2osirixsr:
                series_instance_uid2osirixsr[series_instance_uid].append(osx)
            else:
                series_instance_uid2osirixsr[series_instance_uid] = [osx]

        for series_instance_uid, osirix_sr in series_instance_uid2osirixsr.items():
            series = sorted(series_instance_uid2series[series_instance_uid], key=lambda x:x['fullpath'])
            osirix_sr = sorted(osirix_sr, key=lambda x : SOPInstanceUID_lookup_table[osirix_get_reference_uid(x)].InstanceNumber)
            tmp_dir = osp.join('/tmp/OsirixSR2dicomrt', f'study-{study_instance_uid}/series-{series_instance_uid}')
            os.makedirs(tmp_dir, exist_ok=True)
            for ds in series:
                fullpath = ds.fullpath
                ds = dcmread(fullpath)
                try:
                    ds.pixel_array
                except:
                    warn(f"\"{fullpath}\" cannot access pixel_array")
                fn = osp.basename(fullpath)
                if not hasattr(ds, 'StudyID'):
                    ds.StudyID = study_instance_uid
                ds.save_as(osp.join(tmp_dir, fn))
            #
            try:
                rtstruct  = RTStructBuilder.create_new(dicom_series_path=tmp_dir)
            except:
                warn(f"Cannot create RTStructure for {tmp_dir}")
                continue
            h, w = dcmread(series[0].fullpath).pixel_array.shape
            named_rois = dict()
            up_side_down = series[-1].SliceLocation < series[0].SliceLocation
            for osx in osirix_sr:
                instance_number = int(SOPInstanceUID_lookup_table[osirix_get_reference_uid(osx)].InstanceNumber)
                roi_idx = len(series) - instance_number if up_side_down else instance_number - 1
                rois = osirix_parser(dcmread(osx.fullpath))
                for roi in rois:
                    if roi.name in named_rois:
                        named_rois[roi.name][roi_idx] = Polygon2D(coords=roi.coords.flatten().tolist(), h=h, w=w)
                    else:
                        named_rois[roi.name] = [Polygon2D(coords=[], h=h, w=w)] * len(series)
                        named_rois[roi.name][roi_idx] = Polygon2D(coords=roi.coords.flatten().tolist(), h=h, w=w)
            for name, roi in named_rois.items():
                rtstruct.add_roi(polygon=roi, name=name)
            save_path = osp.join(study_prefix, "RTStructure", f'{series[0].SeriesDescription.replace(" ", "-")}_rtstruct.dcm')
            os.makedirs(osp.dirname(save_path), exist_ok=True)
            print(f"Saved structure set to \"{save_path}\"")
            rtstruct.save(save_path)
            shutil.rmtree(tmp_dir)


if __name__ == "__main__":
    args = parse_args()
    if not osp.isdir(args.dicom):
        raise RuntimeError(f'{args.dicom} is not a directory')
    if args.dicom == '/':
        warn("You are searching dicoms in the root directory, this might be EXTREMELY time-consuming. Consider providing a more specific sub-directory.")
    process(args.dicom)
