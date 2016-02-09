import sys
import subprocess
import scipy
import os

import numpy as np
import multiprocessing as mp



__all__ = ["evaluateNodeFunction"]
__version__ = "0.1"

filepath = os.path.abspath(__file__)
filedir = os.path.dirname(filepath)


def evaluateNodeFunction(data):
    """
    all_data = (cmds, node, tmp_parameter_names, modelfile, modelpath,
                feature_list, feature_cmd, kwargs)
    """
    cmd = data[0]
    supress_model_output = data[1]
    node = data[2]
    tmp_parameter_names = data[3]
    feature_list = data[4]
    feature_cmd = data[5]

    kwargs = data[6]

    if isinstance(node, float) or isinstance(node, int):
        node = [node]

    # New setparameters
    tmp_parameters = {}
    j = 0
    for parameter in tmp_parameter_names:
        tmp_parameters[parameter] = node[j]
        j += 1

    current_process = mp.current_process().name.split("-")
    if current_process[0] == "PoolWorker":
        current_process = str(current_process[-1])
    else:
        current_process = "0"

    cmd = cmd + ["--CPU", current_process, "--save_path", filedir, "--parameters"]

    for parameter in tmp_parameters:
        cmd.append(parameter)
        cmd.append(str(tmp_parameters[parameter]))

    simulation = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    ut, err = simulation.communicate()

    if not supress_model_output:
        print ut

    if simulation.returncode != 0:
        print ut
        print "Error when running simulation:"
        print err
        sys.exit(1)


    U = np.load(os.path.join(filedir, ".tmp_U_%s.npy" % current_process))
    t = np.load(os.path.join(filedir, ".tmp_t_%s.npy" % current_process))

    os.remove(os.path.join(filedir, ".tmp_U_%s.npy" % current_process))
    os.remove(os.path.join(filedir, ".tmp_t_%s.npy" % current_process))



    sys.path.insert(0, feature_cmd[0])
    module = __import__(feature_cmd[1].split(".")[0])

    features = getattr(module, feature_cmd[2])(t, U, **kwargs)
    # features = ImplementedNeuronFeatures(t, V)

    feature_results = features.calculateFeatures(feature_list)

    results = {}
    for feature in feature_results:
        tmp_result = feature_results[feature]

        if hasattr(tmp_result, "__iter__"):
            if len(tmp_result) == 2 and hasattr(tmp_result[0], "__iter__") and hasattr(tmp_result[1], "__iter__"):
                interpolation = scipy.interpolate.InterpolatedUnivariateSpline(t, U, k=3)
                results[feature] = (tmp_result[0], tmp_result[1], interpolation)
            else:
                results[feature] = (None, tmp_result, None)
        else:
            results[feature] = (None, (tmp_result), None)


    interpolation = scipy.interpolate.InterpolatedUnivariateSpline(t, U, k=3)
    results["directComparison"] = (t, U, interpolation)

    # All results are saved as {feature : (x, U, interpolation)} as appropriate.

    return results