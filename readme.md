# OsirixSR to dicom RT convert
Convert OsirixSR annotations to dicom [RT structure](https://dicom.nema.org/dicom/2013/output/chtml/part03/sect_A.19.html).

## Usage
1. clone this repository via: `git clone https://github.com/zeakey/osirixsr2dicomrt.git --recursive`. Don't miss the `--recursive` argument.
2. Execute `python rtconvert.py /path` where `/path` is the folder containing OsirixSR and dicom images on which the annotations were made.

Try the example data with: `python rtconvert.py example/Prostatex-0000`.

Tested on Osirix MD `13.0.2`.

This software is open-sourced under the BY-NC-ND license.
The CC BY-NC license allows others to reuse, adapt, remix, and redistribute the work for any non-commercial purpose; commercial use of the work is not allowed.
