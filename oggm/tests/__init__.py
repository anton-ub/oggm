import six
from distutils.version import LooseVersion
import osgeo.gdal
import os
import sys
import socket
import unittest
import logging
import matplotlib
import pandas as pd
import geopandas as gpd
import numpy as np
import scipy.optimize as optimization
from six.moves.urllib.request import urlopen
from six.moves.urllib.error import URLError
from oggm import cfg

# Defaults
logging.basicConfig(format='%(asctime)s: %(name)s: %(message)s',
                    datefmt='%Y-%m-%d %H:%M:%S', level=logging.DEBUG)

# test dirs
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
TESTDIR_BASE = os.path.join(CURRENT_DIR, 'tmp')

# Some logic to see which environment we are running on

# GDAL version changes the way interpolation is made (sigh...)
HAS_NEW_GDAL = False
if osgeo.gdal.__version__ >= '1.11':
    HAS_NEW_GDAL = True

# Matplotlib version changes plots, too
HAS_MPL_FOR_TESTS = False
if LooseVersion(matplotlib.__version__) >= LooseVersion('2'):
    HAS_MPL_FOR_TESTS = True
    BASELINE_DIR = os.path.join(cfg.CACHE_DIR, 'oggm-sample-data-master',
                                'baseline_images', '2.0.x')


# Some control on which tests to run (useful to avoid too long tests)
# defaults everywhere else than travis
ON_AWS = False
ON_TRAVIS = False
RUN_SLOW_TESTS = False
RUN_DOWNLOAD_TESTS = False
RUN_PREPRO_TESTS = True
RUN_MODEL_TESTS = True
RUN_WORKFLOW_TESTS = True
RUN_GRAPHIC_TESTS = True
RUN_PERFORMANCE_TESTS = False
if os.environ.get('TRAVIS') is not None:
    # specific to travis to reduce global test time
    ON_TRAVIS = True
    RUN_DOWNLOAD_TESTS = False
    matplotlib.use('Agg')

    if sys.version_info < (3, 5):
        # Minimal tests
        RUN_SLOW_TESTS = False
        RUN_PREPRO_TESTS = True
        RUN_MODEL_TESTS = True
        RUN_WORKFLOW_TESTS = True
        RUN_GRAPHIC_TESTS = True
    else:
        # distribute the tests
        RUN_SLOW_TESTS = True
        env = os.environ.get('OGGM_ENV')
        if env == 'prepro':
            RUN_PREPRO_TESTS = True
            RUN_MODEL_TESTS = False
            RUN_WORKFLOW_TESTS = False
            RUN_GRAPHIC_TESTS = False
        if env == 'models':
            RUN_PREPRO_TESTS = False
            RUN_MODEL_TESTS = True
            RUN_WORKFLOW_TESTS = False
            RUN_GRAPHIC_TESTS = False
        if env == 'workflow':
            RUN_PREPRO_TESTS = False
            RUN_MODEL_TESTS = False
            RUN_WORKFLOW_TESTS = True
            RUN_GRAPHIC_TESTS = False
        if env == 'graphics':
            RUN_PREPRO_TESTS = False
            RUN_MODEL_TESTS = False
            RUN_WORKFLOW_TESTS = False
            RUN_GRAPHIC_TESTS = True
elif 'ip-' in socket.gethostname():
    # we are on AWS (hacky way)
    ON_AWS = True
    RUN_SLOW_TESTS = True
    matplotlib.use('Agg')

# give user some control
if os.environ.get('OGGM_SLOW_TESTS') is not None:
    RUN_SLOW_TESTS = True
if os.environ.get('OGGM_DOWNLOAD_TESTS') is not None:
    RUN_DOWNLOAD_TESTS = True

# quick n dirty method to see if internet is on
try:
    _ = urlopen('http://www.google.com', timeout=1)
    HAS_INTERNET = True
except URLError:
    HAS_INTERNET = False


def requires_internet(test):
    # Test decorator
    msg = 'requires internet'
    return test if HAS_INTERNET else unittest.skip(msg)(test)


def requires_py3(test):
    # Test decorator
    msg = "requires python3"
    return unittest.skip(msg)(test) if six.PY2 else test


def requires_mpltest(test):
    # Decorator
    msg = 'requires mpl V1.5+ and matplotlib.testing.decorators'
    return test if HAS_MPL_FOR_TESTS else unittest.skip(msg)(test)


def is_slow(test):
    # Test decorator
    msg = "requires explicit environment for slow tests"
    return test if RUN_SLOW_TESTS else unittest.skip(msg)(test)


def is_download(test):
    # Test decorator
    msg = "requires explicit environment for download tests"
    return test if RUN_DOWNLOAD_TESTS else unittest.skip(msg)(test)

def is_performance_test(test):
    # Test decorator
    msg = "requires explicit environment for performance tests"
    return test if RUN_PERFORMANCE_TESTS else unittest.skip(msg)(test)

# the code below is copy/pasted from xarray
# TODO: go back to xarray when https://github.com/pydata/xarray/issues/754
def assertEqual(a1, a2):
    assert a1 == a2 or (a1 != a1 and a2 != a2)


def decode_string_data(data):
    if data.dtype.kind == 'S':
        return np.core.defchararray.decode(data, 'utf-8', 'replace')


def data_allclose_or_equiv(arr1, arr2, rtol=1e-05, atol=1e-08):
    from xarray.core import ops

    if any(arr.dtype.kind == 'S' for arr in [arr1, arr2]):
        arr1 = decode_string_data(arr1)
        arr2 = decode_string_data(arr2)
    exact_dtypes = ['M', 'm', 'O', 'U']
    if any(arr.dtype.kind in exact_dtypes for arr in [arr1, arr2]):
        return ops.array_equiv(arr1, arr2)
    else:
        return ops.allclose_or_equiv(arr1, arr2, rtol=rtol, atol=atol)


def assertVariableAllClose(v1, v2, rtol=1e-05, atol=1e-08):
    assertEqual(v1.dims, v2.dims)
    allclose = data_allclose_or_equiv(
        v1.values, v2.values, rtol=rtol, atol=atol)
    assert allclose, (v1.values, v2.values)


def assertDatasetAllClose(d1, d2, rtol=1e-05, atol=1e-08):
    assertEqual(sorted(d1, key=str), sorted(d2, key=str))
    for k in d1:
        v1 = d1.variables[k]
        v2 = d2.variables[k]
        assertVariableAllClose(v1, v2, rtol=rtol, atol=atol)


def init_hef(reset=False, border=40, invert_with_sliding=True):

    from oggm.core.preprocessing import gis, centerlines, geometry
    from oggm.core.preprocessing import climate, inversion
    import oggm
    import oggm.cfg as cfg
    from oggm.utils import get_demo_file

    # test directory
    testdir = TESTDIR_BASE + '_border{}'.format(border)
    if not invert_with_sliding:
        testdir += '_withoutslide'
    if not os.path.exists(testdir):
        os.makedirs(testdir)
        reset = True
    if not os.path.exists(os.path.join(testdir, 'RGI40-11.00897')):
        reset = True
    if not os.path.exists(os.path.join(testdir, 'RGI40-11.00897',
                                       'inversion_params.pkl')):
        reset = True

    # Init
    cfg.initialize()
    cfg.PATHS['dem_file'] = get_demo_file('hef_srtm.tif')
    cfg.PATHS['climate_file'] = get_demo_file('histalp_merged_hef.nc')
    cfg.PARAMS['border'] = border

    hef_file = get_demo_file('Hintereisferner.shp')
    entity = gpd.GeoDataFrame.from_file(hef_file).iloc[0]
    gdir = oggm.GlacierDirectory(entity, base_dir=testdir, reset=reset)

    if not reset:
        return gdir

    gis.define_glacier_region(gdir, entity=entity)
    gis.glacier_masks(gdir)
    centerlines.compute_centerlines(gdir)
    centerlines.compute_downstream_lines(gdir)
    geometry.initialize_flowlines(gdir)
    geometry.catchment_area(gdir)
    geometry.catchment_width_geom(gdir)
    geometry.catchment_width_correction(gdir)
    climate.process_histalp_nonparallel([gdir])
    climate.mu_candidates(gdir, div_id=0)
    mbdf = gdir.get_ref_mb_data()['ANNUAL_BALANCE']
    res = climate.t_star_from_refmb(gdir, mbdf)
    climate.local_mustar_apparent_mb(gdir, tstar=res['t_star'][-1],
                                     bias=res['bias'][-1],
                                     prcp_fac=res['prcp_fac'])

    inversion.prepare_for_inversion(gdir)
    ref_v = 0.573 * 1e9

    if invert_with_sliding:
        def to_optimize(x):
            # For backwards compat
            _fd = 1.9e-24 * x[0]
            glen_a = (cfg.N+2) * _fd / 2.
            fs = 5.7e-20 * x[1]
            v, _ = inversion.invert_parabolic_bed(gdir, fs=fs,
                                                  glen_a=glen_a)
            return (v - ref_v)**2

        out = optimization.minimize(to_optimize, [1, 1],
                                    bounds=((0.01, 10), (0.01, 10)),
                                    tol=1e-4)['x']
        _fd = 1.9e-24 * out[0]
        glen_a = (cfg.N+2) * _fd / 2.
        fs = 5.7e-20 * out[1]
        v, _ = inversion.invert_parabolic_bed(gdir, fs=fs,
                                              glen_a=glen_a,
                                              write=True)
    else:
        def to_optimize(x):
            glen_a = cfg.A * x[0]
            v, _ = inversion.invert_parabolic_bed(gdir, fs=0.,
                                                  glen_a=glen_a)
            return (v - ref_v)**2

        out = optimization.minimize(to_optimize, [1],
                                    bounds=((0.01, 10),),
                                    tol=1e-4)['x']
        glen_a = cfg.A * out[0]
        fs = 0.
        v, _ = inversion.invert_parabolic_bed(gdir, fs=fs,
                                              glen_a=glen_a,
                                              write=True)
    d = dict(fs=fs, glen_a=glen_a)
    d['factor_glen_a'] = out[0]
    try:
        d['factor_fs'] = out[1]
    except IndexError:
        d['factor_fs'] = 0.
    gdir.write_pickle(d, 'inversion_params')

    inversion.distribute_thickness(gdir, how='per_altitude',
                                   add_nc_name=True)
    inversion.distribute_thickness(gdir, how='per_interpolation',
                                   add_slope=False, smooth=False,
                                   add_nc_name=True)

    return gdir
