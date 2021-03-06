"""
====================
Simulate alpha waves
====================

This example demonstrates how to simulate alpha waves using
HNN-core.
"""

# Authors: Mainak Jas <mainak.jas@telecom-paristech.fr>
#          Sam Neymotin <samnemo@gmail.com>

import os.path as op

###############################################################################
# Let us import hnn_core

import hnn_core
from hnn_core import simulate_dipole, read_params, Network

###############################################################################
# Then we setup the directories and Neuron
hnn_core_root = op.join(op.dirname(hnn_core.__file__), '..')

###############################################################################
# Then we read the default parameters file
params_fname = op.join(hnn_core_root, 'param', 'default.json')
params = read_params(params_fname)
print(params)

###############################################################################
# Now, we update a few parameters
params.update({
    'dipole_scalefctr': 150000.0,
    'dipole_smooth_win': 0,
    'tstop': 710.0,
    't0_input_prox': 2000.0,
    'tstop_input_prox': 710.0,
    't0_input_dist': 50.0,
    'tstop_input_dist': 1001.0,
    't_evprox_1': 1000,
    'sigma_t_evprox_1': 2.5,
    't_evprox_2': 2000.0,
    'sigma_t_evprox_2': 7.0,
    't_evdist_1': 2000.0,
    'sigma_t_evdist_1': 6.0,
    'input_dist_A_weight_L2Pyr_ampa': 5.4e-5,
    'input_dist_A_weight_L5Pyr_ampa': 5.4e-5,
    'sync_evinput': 1
})

###############################################################################
# And we update all the conductances gbar related to the inputs
# by using the pattern gbar_ev*
params['gbar_ev*'] = 0.0

###############################################################################
# Now let's simulate the dipole and plot it
net = Network(params)
dpl = simulate_dipole(net)
dpl[0].plot()

###############################################################################
# We can confirm that what we simulate is indeed 10 Hz activity.
import matplotlib.pyplot as plt
from scipy.signal import spectrogram
import numpy as np
sfreq = 1000. / params['dt']
n_fft = 1024 * 8
freqs, _, psds = spectrogram(
    dpl[0].dpl['agg'], sfreq, window='hamming', nfft=n_fft,
    nperseg=n_fft, noverlap=0)
plt.figure()
plt.plot(freqs, np.mean(psds, axis=-1))
plt.xlim((0, 40))
plt.xlabel('Frequency (Hz)')
plt.ylabel('PSD')
plt.show()
