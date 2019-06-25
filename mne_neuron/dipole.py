"""Class to handle the dipoles."""

# Authors: Mainak Jas <mainak.jas@telecom-paristech.fr>
#          Sam Neymotin <samnemo@gmail.com>

import numpy as np
from numpy import convolve, hamming


def _hammfilt(x, winsz):
    """Convolve with a hamming window."""
    win = hamming(winsz)
    win /= sum(win)
    return convolve(x, win, 'same')


def get_index_at_time(dpl, t):
    """Check that the time has an index and return it"""
    import numpy as np

    indices = np.where(np.around(dpl.t, decimals=4) == t)[0]
    if len(indices) < 1:
        print("Error, invalid start time for dipole")
        return

    return indices[0]


def initialize_sim(net):
    """
    Initialize NEURON simulation variables

    Parameters
    ----------
    net : Network object
        The Network object with parameter values
    Returns
    -------
    t_vec : Vector
          Vector that has been connected to time ref in NEURON
    """

    from neuron import h
    h.load_file("stdrun.hoc")

    # Set tstop before instantiating any classes
    h.tstop = net.params['tstop']
    h.dt = net.params['dt']  # simulation duration and time-step
    h.celsius = net.params['celsius']  # 37.0 - set temperature

    # create or reinitialize scalars in NEURON (hoc) context
    #h("dp_total_L2 = 0.")
    #h("dp_total_L5 = 0.")

    # Connect NEURON scalar references to python vectors
    t_vec = h.Vector(int(h.tstop / h.dt + 1)).record(h._ref_t)  # time recording

    return t_vec


def simulate_dipole(net, trial=0, verbose=True, extdata=None):
    """Simulate a dipole given the experiment parameters.

    Parameters
    ----------
    net : Network object
        The Network object specifying how cells are
        connected.
    trial : int
        Current trial number
    verbose: bool
        False will turn off "Simulation time" messages
    extdata : np.Array | None
        Array with preloaded data to compare simulation
        results against

    Returns
    -------
    dpl: instance of Dipole
        The dipole object
    """
    from .parallel import rank, nhosts, pc, cvode

    from neuron import h
    h.load_file("stdrun.hoc")
    t_vec = initialize_sim(net)

    # make sure network state is consistent
    net.state_init()

    if trial != 0:
        # for reproducibility of original HNN results
        net.reset_src_event_times()

    pc.setup_transfer()
    # Now let's simulate the dipole

    if verbose:
        pc.barrier()  # sync for output to screen
        if rank == 0:
            print("Running trial %d (on %d cores)" % (trial + 1, nhosts))

    # initialize cells to -65 mV, after all the NetCon
    # delays have been specified
    h.finitialize()

    def prsimtime():
        print('Simulation time: {0} ms...'.format(round(h.t, 2)))

    printdt = 10
    if verbose and rank == 0:
        for tt in range(0, int(h.tstop), printdt):
            cvode.event(tt, prsimtime)  # print time callbacks

    h.fcurrent()

    #pc.barrier()  # get all nodes to this place before continuing

    # actual simulation - run the solver
    pc.psolve(h.tstop)

    # aggregate the currents independently on each proc
    net.aggregate_currents()
    net.aggregate_dpls()
    # get all nodes to this place before continuing
    pc.barrier()

    # these calls aggregate data across procs/nodes
    # combine dp_rec on every node, 1=add contributions together
    pc.allreduce(net.dpls['L5Pyr'], 1)
    pc.allreduce(net.dpls['L2Pyr'], 1)
    pc.allreduce(net.current['L5Pyr_soma'], 1)
    pc.allreduce(net.current['L2Pyr_soma'], 1)

    dpl = None
    if rank == 0:
        dpl_data = np.c_[np.array(net.dpls['L2Pyr'].to_python()) +
                        np.array(net.dpls['L5Pyr'].to_python()),
                        np.array(net.dpls['L2Pyr'].to_python()),
                        np.array(net.dpls['L5Pyr'].to_python())]

        dpl = Dipole(np.array(t_vec.to_python()), dpl_data)

    err = 0
    if rank == 0:
        #dpl.baseline_renormalize(net.params)
        #dpl.convert_fAm_to_nAm()
        #dpl.scale(net.params['dipole_scalefctr'])
        #dpl.smooth(net.params['dipole_smooth_win'] / h.dt)

        if net.params['save_dpl']:
            dpl.write('dpl_%d.txt' % trial)

    return dpl


def average_dipoles(dpls):
    """Compute average over a list of Dipole objects.

    Parameters
    ----------
    dpls: list of Dipole objects
        Contains list of dipole results to be averaged

    Returns
    -------
    dpl: instance of Dipole
        A dipole object with averages of the dipole data
    """

    # need at least on Dipole to get times
    assert (len(dpls) > 0)

    agg_avg = np.mean(np.array([dpl.dpl['agg'] for dpl in dpls]), axis=0)
    L5_avg = np.mean(np.array([dpl.dpl['L5'] for dpl in dpls]), axis=0)
    L2_avg = np.mean(np.array([dpl.dpl['L2'] for dpl in dpls]), axis=0)

    avg_dpl_data = np.c_[agg_avg,
                         L2_avg,
                         L5_avg]

    avg_dpl = Dipole(dpls[0].t, avg_dpl_data)

    return avg_dpl


class Dipole(object):
    """Dipole class.

    Parameters
    ----------
    times : array (n_times,)
        The time vector
    data : array (n_times x 3)
        The data. The first column represents 'agg',
        the second 'L2' and the last one 'L5'

    Attributes
    ----------
    t : array
        The time vector
    dpl : dict of array
        The dipole with key 'agg' and optionally, 'L2' and 'L5'
    """

    def __init__(self, times, data):  # noqa: D102
        self.units = 'fAm'
        self.N = data.shape[0]
        self.t = times
        self.dpl = {}
        self.dpl['agg'] = data[:, 0]
        self.dpl['L2'] = data[:, 1]
        self.dpl['L5'] = data[:, 2]

    # conversion from fAm to nAm
    def convert_fAm_to_nAm(self):
        """ must be run after baseline_renormalization()
        """
        for key in self.dpl.keys():
            self.dpl[key] *= 1e-6
        self.units = 'nAm'

    def scale(self, fctr):
        for key in self.dpl.keys():
            self.dpl[key] *= fctr
        return fctr

    def smooth(self, winsz):
        # XXX: add check to make sure self.t is
        # not smaller than winsz
        if winsz <= 1:
            return
        for key in self.dpl.keys():
            self.dpl[key] = _hammfilt(self.dpl[key], winsz)

    def plot(self, ax=None, layer='agg'):
        """Simple layer-specific plot function.

        Parameters
        ----------
        ax : instance of matplotlib figure | None
            The matplotlib axis
        layer : str
            The layer to plot
        show : bool
            If True, show the figure

        Returns
        -------
        fig : instance of plt.fig
            The matplotlib figure handle.
        """
        import matplotlib.pyplot as plt

        if ax is None:
            fig, ax = plt.subplots(1, 1)
        if layer in self.dpl.keys():
            ax.plot(self.t, self.dpl[layer])
            ax.set_xlabel('Time (ms)')
        if True:
            plt.show()
        return ax.get_figure()

    def baseline_renormalize(self, params):
        """Only baseline renormalize if the units are fAm.

        Parameters
        ----------
        params : dict
            The parameters
        """
        if self.units != 'fAm':
            print("Warning, no dipole renormalization done because units"
                  " were in %s" % (self.units))
            return
        elif (not 'L2' in self.dpl) and (not 'L5' in self.dpl):
            print("Warning, no dipole renormalization done because"
                  " L2 and L5 components are not available")
            return

        N_pyr_x = params['N_pyr_x']
        N_pyr_y = params['N_pyr_y']
        # N_pyr cells in grid. This is PER LAYER
        N_pyr = N_pyr_x * N_pyr_y
        # dipole offset calculation: increasing number of pyr
        # cells (L2 and L5, simultaneously)
        # with no inputs resulted in an aggregate dipole over the
        # interval [50., 1000.] ms that
        # eventually plateaus at -48 fAm. The range over this interval
        # is something like 3 fAm
        # so the resultant correction is here, per dipole
        # dpl_offset = N_pyr * 50.207
        dpl_offset = {
            # these values will be subtracted
            'L2': N_pyr * 0.0443,
            'L5': N_pyr * -49.0502
            # 'L5': N_pyr * -48.3642,
            # will be calculated next, this is a placeholder
            # 'agg': None,
        }
        # L2 dipole offset can be roughly baseline shifted over
        # the entire range of t
        self.dpl['L2'] -= dpl_offset['L2']
        # L5 dipole offset should be different for interval [50., 500.]
        # and then it can be offset
        # slope (m) and intercept (b) params for L5 dipole offset
        # uncorrected for N_cells
        # these values were fit over the range [37., 750.)
        m = 3.4770508e-3
        b = -51.231085
        # these values were fit over the range [750., 5000]
        t1 = 750.
        m1 = 1.01e-4
        b1 = -48.412078
        # piecewise normalization
        self.dpl['L5'][self.t <= 37.] -= dpl_offset['L5']
        self.dpl['L5'][(self.t > 37.) & (self.t < t1)] -= N_pyr * \
            (m * self.t[(self.t > 37.) & (self.t < t1)] + b)
        self.dpl['L5'][self.t >= t1] -= N_pyr * \
            (m1 * self.t[self.t >= t1] + b1)
        # recalculate the aggregate dipole based on the baseline
        # normalized ones
        self.dpl['agg'] = self.dpl['L2'] + self.dpl['L5']

    def write(self, fname):
        """Write dipole values to a file.

        Parameters
        ----------
        fname : str
            Full path to the output file (.txt)
        """
        cols = [self.dpl.get(key) for key in ['agg', 'L2', 'L5'] if (key in self.dpl)]
        X = np.r_[[self.t] + cols].T
        np.savetxt(fname, X, fmt=['%3.3f', '%5.4f', '%5.4f', '%5.4f'],
                   delimiter='\t')

    def rmse(self, exp_dpl, tstart, tstop):
        """ Calculates RMSE compared to data in exp_dpl """
        from numpy import sqrt
        from scipy import signal

        # make sure start and end times are valid for both dipoles
        sim_start_index = get_index_at_time(self, tstart)
        sim_end_index = get_index_at_time(self, tstop)
        sim_length = sim_end_index - sim_start_index

        exp_start_index = get_index_at_time(exp_dpl, tstart)
        exp_end_index = get_index_at_time(exp_dpl, tstop)
        exp_length = exp_end_index - exp_start_index


        dpl1 = self.dpl['agg'][sim_start_index:sim_end_index]
        dpl2 = exp_dpl.dpl['agg'][exp_start_index:exp_end_index]
        if (sim_length > exp_length):
            # downsample simulation timeseries to match exp data
            dpl1 = signal.resample(dpl1, exp_length)
        elif (sim_length < exp_length):
            # downsample exp timeseries to match simulation data
            dpl2 = signal.resample(dpl2, sim_length)

        return sqrt(((dpl1 - dpl2) ** 2).mean())
