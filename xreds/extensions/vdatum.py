import xarray as xr

from xreds.dataset_extension import DatasetExtension, hookimpl
from xreds.logging import logger
from xreds.utils import load_dataset


def transform_datum(
    ds: xr.Dataset,
    ds_vdatum: xr.Dataset,
    target_zeta_var: str,
    target_datum_var: str,
    target_datum_name: str,
    out_datum_var: str,
) -> xr.Dataset:
    """Transform the dataset to target datum

    Args:
        ds (xr.Dataset): The dataset to transform
        ds_vdatum (xr.Dataset): The vdatum dataset

    Returns:
        xr.Dataset: The transformed dataset
    """
    datum = ds_vdatum[target_datum_var]
    zeta = ds[target_zeta_var]

    datum_dims = [k for k in datum.dims]
    target_dims = [k for k in zeta.dims]
    target_dims = target_dims[-len(datum_dims) :]
    new_dims = {o: k for (o, k) in zip(datum_dims, target_dims)}

    # validate
    for o, k in new_dims.items():
        assert ds_vdatum[target_datum_var][o].shape == ds.zeta[k].shape

    zeta_to_datum = zeta + datum.rename(new_dims)
    zeta_to_datum = zeta_to_datum.assign_attrs({"datum": target_datum_name})

    ds_transformed = ds.assign({out_datum_var: zeta_to_datum})
    return ds_transformed


class VDatumTransformationExtension(DatasetExtension):
    """VDatum transformation extension"""

    name: str = "vdatum"

    @hookimpl
    def transform_dataset(self, ds: xr.Dataset, config: dict) -> xr.Dataset:
        """Transform a dataset"""
        if "zeta" not in ds.variables:
            logger.warning(
                f"Dataset {ds.attrs.get('name', 'unknown')} does not have a zeta variable. Skipping vdatum transformation"
            )
            return ds

        vdatum_file = config.get("path", None)
        if vdatum_file is None:
            logger.warning(
                f"Dataset {ds.attrs.get('name', 'unknown')} does not have a vdatum_path attribute. Skipping vdatum transformation"
            )
            return ds

        ds_vdatum = load_dataset({"path": vdatum_file})
        if ds_vdatum is None:
            logger.warning(
                f"Could not load vdatum dataset from {vdatum_file}. Skipping vdatum transformation"
            )
            return ds
        
        target_zeta_var = config.get("water_level_var", "zeta")
        target_datum_var = config.get("vdatum_var", "igld85tolwd")
        target_datum_name = config.get("vdatum_name", "igld85")
        out_datum_var = f"{target_zeta_var}_{target_datum_name}"

        ds_transformed = transform_datum(ds, ds_vdatum, target_zeta_var, target_datum_var, target_datum_name, out_datum_var)
        return ds_transformed
