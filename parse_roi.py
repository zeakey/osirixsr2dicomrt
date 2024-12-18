import csv, json, cv2
import numpy as np
from warnings import warn
from dicom_utils import dotdict


def parse_json(fn: str):
    data = json.load(open(fn, "r"))
    if "Images" not in data or len(data["Images"]) == 0 or len(data["Images"][0]["ROIs"]) == 0:
        warn(f"No ROI found in {fn}.")
        return
    data = data["Images"]
    SeriesInstanceUID = data[0]["ROIs"][0]["SeriesInstanceUID"]
    StudyInstanceUID = data[0]["ROIs"][0]["StudyInstanceUID"]
    h, w, d = data[0]["ImageHeight"], data[0]["ImageWidth"], data[0]["ImageTotalNum"]

    results = dict(
        StudyInstanceUID=StudyInstanceUID,
        SeriesInstanceUID=SeriesInstanceUID
    )

    roi_names = [roi["Name"] for image in data for roi in image["ROIs"]]

    named3dmask = dotdict()
    for name in roi_names:
        named3dmask[name] = np.zeros((h, w, d), dtype=bool)

    for image in data:
        ImageIndex = image["ImageIndex"]
        assert image["ImageHeight"] == h and image["ImageWidth"] == w

        for roi in image["ROIs"]:
            name = roi["Name"]
            if name not in named3dmask:
                named3dmask[name] = np.zeros((h, w, d), dtype=bool)
            points = np.array([eval(point) for point in roi['Point_px']])

            assert roi["SeriesInstanceUID"] == SeriesInstanceUID
            assert roi["StudyInstanceUID"] == StudyInstanceUID

            mask1 = named3dmask[name][:, :, ImageIndex].astype(np.uint8)
            cv2.fillPoly(mask1, [points.astype(np.int32)], color=1)
            named3dmask[name][:, :, ImageIndex] = mask1.astype(bool)
    
    results["named3dmask"] = named3dmask
    return dotdict(results)


def parse_csv(fn):
    table = list(csv.reader(open(fn, "r")))
    header = table[0]
    def key2idx(key: str):
        if key in header: 
            return table[0].index(key)
        else:
            raise ValueError(f"Unknown key={key} in header {header}.")

    keys = ["ImageNo", "RoiName", "SOPInstanceUID", "StudyInstanceUID", "SeriesInstanceUID"]

    rois = []
    for row in table[1:]:
        roi = dict()
        for k in keys:
            roi[k] = row[key2idx(k)]
        # parse points
        num_points = int(row[key2idx("NumOfPoints")])
        point_start_idx = key2idx("mmX")
        assert len(row[point_start_idx:]) == num_points * 5
        points = np.array(row[point_start_idx:], dtype=np.float32).reshape(num_points, 5)
        #
        roi["points_mm"], roi["points_px"] = np.hsplit(points, [3])
        roi["num_points"] = num_points
        rois.append(roi)

    for roi in rois:
        assert roi["SeriesInstanceUID"] == rois[0]["SeriesInstanceUID"] and \
            roi["StudyInstanceUID"] == rois[0]["StudyInstanceUID"]

    return rois


if __name__ == "__main__":
    parse_json("/Users/kzhao/Documents/micro-us/mus_lesion/7082987/study/Sun,Andrew-10:24:23-In-Vivo US scan of prostate.json")
