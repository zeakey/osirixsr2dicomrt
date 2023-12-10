import pydicom
import os.path as osp
import pathlib
from glob import glob
import logging
from warnings import warn
from tqdm import tqdm


class dotdict(dict):
    """dot.notation access to dictionary attributes"""
    __getattr__ = dict.get
    __setattr__ = dict.__setitem__
    __delattr__ = dict.__delitem__


def get_logger(log_file):
    logger = logging.getLogger("RTConvert")
    stream_handler = logging.StreamHandler()
    handlers = [stream_handler]
    file_handler = logging.FileHandler(log_file, 'w')
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    for handler in handlers:
            handler.setFormatter(formatter)
            handler.setLevel(logging.INFO)
            logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return logger


def is_osirix_sr(ds):
    return hasattr(pydicom.dcmread(ds.fullpath), "EncapsulatedDocument")


def osirix_get_reference_uid(ds):
    return pydicom.dcmread(ds.fullpath).ContentSequence[0].ReferencedSOPSequence[0].ReferencedSOPInstanceUID


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
        InstanceNumber = ds.InstanceNumber if hasattr(ds, 'InstanceNumber') else None
        ds = dict(
            fullpath=d,
            SeriesDescription=ds.SeriesDescription if hasattr(ds, "SeriesDescription") else "",
            SeriesInstanceUID=ds.SeriesInstanceUID,
            SOPInstanceUID=ds.SOPInstanceUID,
            StudyInstanceUID=ds.StudyInstanceUID,
            InstanceNumber=InstanceNumber,
            SliceLocation=float(ds.SliceLocation) if hasattr(ds, 'SliceLocation') else None,
            is_osirix_sr=hasattr(ds, 'EncapsulatedDocument'))
        ds = dotdict(ds)
        results.append(ds)
    return results


def group_into_studies(dicoms):
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



def group_study_into_series(dicoms):
    """
    group dicoms of the same study into different series according to their `SeriesInstanceUID`
    """
    series = dict()
    for ds in dicoms:
        if ds.SeriesInstanceUID not in series:
            series[ds.SeriesInstanceUID] = [ds]
        else:
            series[ds.SeriesInstanceUID].append(ds)
    return series


def build_SOPInstanceUID_lookup_table(dicoms):
    SOPInstanceUID_lookup_table = dict()
    for ds in dicoms:
        SOPInstanceUID_lookup_table[ds.SOPInstanceUID] = ds
    return SOPInstanceUID_lookup_table


def find_osirix_sr(dicoms):
    """
    find OsirixSR files from given list of dicom files
    """
    return [ds for ds in dicoms if ds.is_osirix_sr]
