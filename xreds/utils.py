import fsspec
import xarray as xr

from xreds.logging import logger


def infer_dataset_type(dataset_path: str) -> str:
    if dataset_path.endswith('.nc'):
        return 'netcdf'
    elif dataset_path.endswith('.grib2'):
        return 'grib2'
    elif dataset_path.endswith('.nc.zarr') or dataset_path.endswith('json'):
        return 'kerchunk'
    elif dataset_path.endswith('.zarr') :
        return 'zarr'

    return 'unknown'


def load_dataset(dataset_spec: dict) -> xr.Dataset | None:
    """Load a dataset from a path"""
    ds = None
    dataset_path = dataset_spec['path']
    dataset_type = dataset_spec.get("type", None)
    if not dataset_type:
        dataset_type = infer_dataset_type(dataset_path)
        logger.info(f"Inferred dataset type {dataset_type} for {dataset_path}")
    if dataset_type == 'unknown':
        logger.error(f"Could not infer dataset type for {dataset_path}")
        return None

    chunks = dataset_spec.get('chunks', None)
    drop_variables = dataset_spec.get('drop_variables', None)
    additional_coords = dataset_spec.get('additional_coords', None)
    additional_attrs = dataset_spec.get('additional_attrs', None)
    key = dataset_spec.get('key', None)
    secret = dataset_spec.get('secret', None)

    if dataset_type == 'netcdf':
        ds = xr.open_dataset(dataset_path, engine='netcdf4', chunks=chunks, drop_variables=drop_variables)
        if additional_coords is not None:
            ds = ds.set_coords(additional_coords)
    elif dataset_type == 'grib2':
        ds = xr.open_dataset(dataset_path, engine='cfgrib')
    elif dataset_type == 'kerchunk':
        if key is not None:
            options = {'anon': False, 'key': key, 'secret': secret}
        else:
            options = {'anon': True}
        fs = fsspec.filesystem(
            "filecache",
            expiry_time=10 * 60, # TODO: Make this driven by config per dataset, for now default to 10 minutes
            target_protocol='reference',
            target_options={
                'fo': dataset_path,
                'target_protocol': 's3',
                'target_options': options,
                'remote_protocol': 's3',
                'remote_options': options,
            })
        m = fs.get_mapper("")
        ds = xr.open_dataset(m, engine="zarr", backend_kwargs=dict(consolidated=False), chunks=chunks, drop_variables=drop_variables)
        try:
            if ds.cf.coords['longitude'].dims[0] == 'longitude':
                ds = ds.assign_coords(longitude=(((ds.longitude + 180) % 360) - 180)).sortby('longitude')
                # TODO: Yeah this should not be assumed... but for regular grids we will viz with rioxarray so for now we will assume
                ds = ds.rio.write_crs(4326)
        except Exception as e:
            logger.warning(f'Could not reindex longitude: {e}')
            pass
    elif dataset_type == 'zarr':
        # TODO: Enable S3  support
        # mapper = fsspec.get_mapper(dataset_location)
        ds = xr.open_zarr(dataset_path, consolidated=True)

    if ds is None:
        return None

    # Add additional attributes to the dataset if provided
    if additional_attrs is not None:
        ds.attrs.update(additional_attrs)
    
    # Check if we have a time dimension and if it is not indexed, index it
    try:
        time_dim = ds.cf['time'].dims[0]
        if not ds.indexes.get(time_dim, None):
            time_coord = ds.cf['time'].name
            logger.info(f'Indexing time dimension {time_dim} as {time_coord}')
            ds = ds.set_index({time_dim: time_coord})
            if 'standard_name' not in ds[time_dim].attrs:
                ds[time_dim].attrs['standard_name'] = 'time'
    except Exception as e:
        logger.warning(f'Could not index time dimension: {e}')
        pass

    return ds