import numpy as np
import nibabel as nib
import os.path as osp
from rt_utils import RTStructBuilder
from rt_utils.image_helper import get_pixel_to_patient_transformation_matrix

# path to your dicom files
dicom_dir = "example/DICOM/"

# path to your dicom rt file
rt_path="example/RTStructure/rtstruct.dcm"


rtstruct = RTStructBuilder.create_from(
    dicom_series_path=dicom_dir,
    rt_struct_path=rt_path
)

affine = get_pixel_to_patient_transformation_matrix(rtstruct.series_data)

roi_names = rtstruct.get_roi_names()

# save the pixel values into nifti
pixel_data = [d.pixel_array[:, :, None] for d in rtstruct.series_data]
pixel_data = np.concatenate(pixel_data, axis=-1)

nifti_img = nib.Nifti1Image(pixel_data, affine=affine)
nifti_img_path = osp.abspath(osp.join(dicom_dir, "..", "images.nii.gz"))
nib.save(nifti_img, nifti_img_path)
print(f"Images saved to f{nifti_img_path}.")


for name in roi_names:
    mask = rtstruct.get_roi_mask_by_name(name).astype(np.float32)
    nifti_mask = nib.Nifti1Image(mask, affine=affine)
    nifti_mask_path = osp.abspath(osp.join(dicom_dir, "..", f"ROI-{name}.nii.gz"))
    nib.save(nifti_mask, nifti_mask_path)
    print(f"ROI saved to f{nifti_mask_path}.")
