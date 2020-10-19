import os.path as op
import io
from contextlib import redirect_stdout, redirect_stderr
import pytest

import hnn_core
from hnn_core import read_params
from hnn_core.mpi_child import MPISimulation
from hnn_core.parallel_backends import MPIBackend


def test_child_run():
    """Test running the MPI child process"""

    hnn_core_root = op.dirname(hnn_core.__file__)

    # prepare params
    params_fname = op.join(hnn_core_root, 'param', 'default.json')
    params = read_params(params_fname)
    params_reduced = params.copy()
    params_reduced.update({'N_pyr_x': 3,
                           'N_pyr_y': 3,
                           'tstop': 25,
                           't_evprox_1': 5,
                           't_evdist_1': 10,
                           't_evprox_2': 20,
                           'N_trials': 2})

    with MPISimulation(skip_MPI_import=True) as mpi_sim:
        with io.StringIO() as buf, redirect_stdout(buf):
            sim_data = mpi_sim.run(params_reduced)
            stdout = buf.getvalue()
        assert "end_of_sim" in stdout

        with io.StringIO() as buf_err, redirect_stderr(buf_err):
            with io.StringIO() as buf_out, redirect_stdout(buf_out):
                mpi_sim._write_data_stderr(sim_data)
                stdout = buf_out.getvalue()
            stderr = buf_err.getvalue()
        assert "end_of_data:" in stdout

        split_stdout = stdout.split('end_of_data:')
        data = stderr.encode()
        data_len = len(data)
        expected_len = int(split_stdout[1])
        print("len data: %d, expected: %d" % (data_len, expected_len))
        backend = MPIBackend()
        sim_data = backend._process_child_data(data, data_len)


def test_empty_data():
    """Test that an empty string raises RuntimeError"""
    data_bytes = b''
    data_len = len(data_bytes)
    backend = MPIBackend()
    with pytest.raises(RuntimeError, match="MPI simulation didn't return any "
                       "data"):
        backend._process_child_data(data_bytes, data_len)


def test_data_len_mismatch():
    """Test that an unexpected data length raises RuntimeError"""
    data_bytes = b'\0'
    data_len = 2
    backend = MPIBackend()
    with pytest.raises(RuntimeError, match="Failed to receive all data from "
                       "the child MPI process. Expecting 2 bytes, got 1"):
        backend._process_child_data(data_bytes, data_len)


def test_data_padding():
    """Test that an incorrect amount of padding raises RuntimeError"""

    import pickle
    import codecs

    pickled_str = pickle.dumps({})
    pickled_bytes = codecs.encode(pickled_str, 'base64')
    pickled_bytes += b'='
    data_len = 10
    backend = MPIBackend()
    with pytest.raises(RuntimeError, match="Incorrect padding for data length "
                       " 10 bytes (mod 4 = 2)"):
        backend._process_child_data(pickled_bytes, data_len)
