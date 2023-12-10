import re
import numpy as np
from typing import Any


class ROI(object):
    def __init__(self, name, coords) -> None:
        self.name = name
        self.coords = coords
    def __repr__(self) -> str:
        return f"ROI(name={self.name}, coords={str(self.coords)})"

def index_all(string, substring):
    start = -1
    indice = []
    while True:
        try:
            start = string.index(substring, start+1)
            if start == -1:
                break
            else:
                indice.append(start)
        except:
            break
    return indice


class OsirixSRParser(object):
    def __init__(self, version='13.0.1') -> None:
        self.version = version

    @staticmethod
    def parse(osx):
        uint8 = np.array(list(osx.EncapsulatedDocument))
        rois = []
        # tmp = decode.replace(chr(0), "").replace(chr(14), "").replace(chr(32), "")
        tmp = ''.join([chr(i) for i in uint8[np.logical_not((uint8 == 0) + (uint8 == 14) + (uint8 == 32))]])
        marker = ''.join([chr(i) for i in range(33, 66)])
        roi_loc = index_all(tmp, marker)
        if len(roi_loc) > 0:
            num_roi = len(roi_loc)
            roi_loc.append(len(tmp))

            for i in range(num_roi):
                txt1 = tmp[roi_loc[i]:roi_loc[i+1]+1]
                abc1 = index_all(txt1, '_')
                if len(abc1) == 0:
                    abc1 = index_all(txt1,'_')
                if len(abc1) != 0:
                    abc2 = np.array(index_all(txt1[abc1[0]:], '}Ò')) + abc1[0]
                # abc2 = np.array(index_all(txt1[abc1[0]:-1], '}Ò')) + abc1[0] - 1
                points = []
                for ind2 in range(len(abc1)):
                    txt2 = txt1[abc1[ind2]:abc2[ind2]+1]
                    endofpoint = abc2[ind2]
                    if len(txt2) > 44:
                        tt = txt2.index('}')
                        txt2 = txt2[1:tt]
                        endofpoint = abc1[ind2] + tt
                    pt = re.findall('\d+\.\d+,\d+\.\d+', txt2)
                    pt = np.array(pt[0].split(','), dtype=np.float32)[None, :]
                    points.append(pt)
                txt3 = txt1[endofpoint-1:abc2[-1]+1]

                #regex = r"}(.*)+"
                #regex = r"}[a-zA-Z]+|{[^{}]+_"
                # regex = r"(?<=\})([a-zA-Z0-9]+)(?=\_)"
                matches = re.findall(r'\}\}(.*?)\_', txt3)
                if len(matches) == 0:
                    matches = re.findall(r'\}(.*?)\_', txt3)
                if len(matches) < 1:
                    raise RuntimeError(f"Cannot parse name of roi\#{i}")
                else:
                    name = matches[0]
                    if len(name) > 0:
                        if len(name) > 2 and name[-1] == "P":
                            name = name[0:-1]
                        if name[-1] == "P" and i > 0:
                            name = rois[i-1]['name']
                        else:
                            name = name[1:]
                    else:
                        if i > 0 and rois[i-1].name:
                            name = rois[i-1].name
                        else:
                            name = "Couldn't parse ROI name from OsirixSR"
                points = np.concatenate(points, axis=0)
                rois.append(ROI(name, points))
        return rois

    def __call__(self, *args: Any, **kwds: Any) -> Any:
        return self.parse(*args, **kwds)
