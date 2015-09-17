# TODO Test out different types of polynomial chaos methods

# TODO Do dependent variable stuff

# TODO Do a mc analysis after u_hat is generated

# TODO Instead of giving results as an average of the response, make it
# feature based. For example, count the number of spikes, and the
# average the number of spikes and time between spikes.

# TODO Make a data selection process before PC expansion to look at
# specific features. This data selection should be the same as what is
# done for handling spikes from experiments. One example is a low pass
# filter and a high pass filter.

# TODO Use a recursive neural network

# TODO Compare with a pure MC calculation

# TODO Atm parameter are both in the model object and in the parameter object.
# Make it so they only are one place?

# TODO Can remove the uncertain parameter and instead test if the parameter has a
# distribution function?

# TODO Parallelize the model evaluations

import time
import datetime
import scipy.interpolate
import os
import sys
import subprocess

import numpy as np
import chaospy as cp
import matplotlib.pyplot as plt
import multiprocess as mp

from xvfbwrapper import Xvfb

from prettyPlot import prettyPlot
from memory import Memory
from distribution import Distribution
from model import Model
from parameters import Parameters


class UncertaintyEstimations():
    def __init__(self, model, uncertain_parameters, distributions, outputdir="figures/"):

        self.UncertaintyEstimations = []

        self.model = model
        self.uncertain_parameters = uncertain_parameters
        self.distributions = distributions
        self.outputdir = outputdir

        self.initialize()


    def initialize(self):
        for distribution_function in self.distributions:
            print self.distributions[distribution_function]
            for interval in self.distributions[distribution_function]:
                current_outputdir = os.path.join(self.outputdir,
                                                 distribution_function + "_%g" % interval)
                distribution = getattr(Distribution(interval), distribution_function)
                parameters = Parameters(self.model.parameters, distribution,
                                        self.uncertain_parameters)
                self.UncertaintyEstimations.append(UncertaintyEstimation(self.model, parameters,
                                                                         current_outputdir))

    def exploreParameters(self):
        for uncertaintyEstimation in self.UncertaintyEstimations:
            run_name = uncertaintyEstimation.outputdir.split("/")[-1].split("_")
            print "Running for: " + run_name[0] + " " + run_name[1]

            uncertaintyEstimation.singleParameters()
            uncertaintyEstimation.allParameters()

    def timePassed(self):
        return self.UncertaintyEstimations[0].timePassed()



class UncertaintyEstimation():
    def __init__(self, model, parameters, outputdir="figures/", supress_output=True):
        """
        model: Model object
        parameters: Parameter object
        outputdir: Where to save the results. Default = "figures/"
        """

        self.outputdir = outputdir
        self.parameters = parameters

        self.parameter_names = None
        self.parameter_space = None

        self.supress_output = supress_output

        self.figureformat = ".png"
        self.t_start = time.time()

        self.model = model

        self.features = []
        self.M = 3
        self.mc_samples = 10**3


        self.U_hat = None
        self.distribution = None
        self.solves = None
        self.t = None
        self.P = None
        self.nodes = None
        self.sensitivity = None
        self.Corr = None

        if not os.path.isdir(self.outputdir):
            os.makedirs(self.outputdir)

    def runParallel(self, node):
        if isinstance(node, float) or isinstance(node, int):
                node = [node]

        # New setparameters
        tmp_parameters = {}
        j = 0
        for parameter in self.tmp_parameter_name:
            tmp_parameters[parameter] = node[j]
            j += 1

        if self.supress_output:
            vdisplay = Xvfb()
            vdisplay.start()

#        sim = Simulation(self.model.modelfile, self.model.modelpath)
        self.model.runParallel(tmp_parameters)
        #V, t = self.model.runParallel(tmp_parameters)
        #self.model.run(tmp_parameters)

        if self.supress_output:
            vdisplay.stop()


        V = np.load("tmp_U.npy")
        t = np.load("tmp_t.npy")

        # Do a feature selection here. Make it so several feature
        # selections are performed at this step.
        for feature in self.features:
            V = feature(V)

        interpolation = scipy.interpolate.InterpolatedUnivariateSpline(t, V, k=3)
        return (t, V, interpolation)


    def createPCExpansion(self, parameter_name=None):

        # TODO find a good way to solve the parameter_name poblem
        if parameter_name is None:
            parameter_space = self.parameters.getUncertain("parameter_space")
            self.tmp_parameter_name = self.parameters.getUncertain("name")
        else:
            parameter_space = [self.parameters.get(parameter_name).parameter_space]
            self.tmp_parameter_name = [parameter_name]



        self.distribution = cp.J(*parameter_space)
        self.P = cp.orth_ttr(self.M, self.distribution)
        nodes = self.distribution.sample(2*len(self.P), "M")
        # TODO problems with rule="P","Z","J"
        #nodes, weights = cp.generate_quadrature(3+1, self.distribution, rule="J", sparse=True)

        # TODO parallelize this loop


        def f(nodes):
            return nodes

        def runParallelFunction(all_data):
            """
            all_data = (node, tmp_parameter_name, modelfile, modelpath, features)
            """

            node = all_data[0]
            tmp_parameter_name = all_data[1]
            modelfile = all_data[2]
            modelpath = all_data[3]
            features = all_data[4]


            print "haha"
            print modelfile
            print modelpath
            if isinstance(node, float) or isinstance(node, int):
                    node = [node]

            # New setparameters
            tmp_parameters = {}
            j = 0
            for parameter in tmp_parameter_name:
                tmp_parameters[parameter] = node[j]
                j += 1

            vdisplay = Xvfb()
            vdisplay.start()

            from simulation import Simulation
            sim = Simulation(modelfile, modelpath)
            sim.set(tmp_parameters)
            sim.runSimulation()
            V = sim.getV()
            t = sim.getT()

            vdisplay.stop()

            # Do a feature selection here. Make it so several feature
            # selections are performed at this step.
            for feature in features:
                V = feature(V)

            interpolation = scipy.interpolate.InterpolatedUnivariateSpline(t, V, k=3)
            return (t, V, interpolation)

        #pool = mp.Pool(1)
        #solves = pool.map(self.parallel, nodes.T)
        #solves = pool.map(f, nodes.T)


        # Create all_data
        all_data = []
        for node in nodes.T:
            all_data.append((node, self.tmp_parameter_name, modelfile, modelpath, self.features))

        print all_data[0]

        solves = []
        # for node in nodes.T:
        #     solves.append(self.runParallel(node))
        for data in all_data:
            solves.append(runParallelFunction(data))

        solves = np.array(solves)
        lengths = []
        for s in solves[:, 0]:
            lengths.append(len(s))

        index_max_len = np.argmax(lengths)
        self.t = solves[index_max_len, 0]

        interpolated_solves = []
        for inter in solves[:, 2]:
            interpolated_solves.append(inter(self.t))

        #self.U_hat = cp.fit_quadrature(self.P, nodes, weights, interpolated_solves)
        self.U_hat = cp.fit_regression(self.P, nodes, interpolated_solves, rule="T")



    def pseudoMC(self, parameter_name=None, feature=None):
        if parameter_name is None:
            parameter_space = self.parameters.getUncertain("parameter_space")
            parameter_name = self.parameters.getUncertain("name")
        else:
            parameter_space = [self.parameters.get(parameter_name).parameter_space]
            parameter_name = [parameter_name]

        self.distribution = cp.J(*parameter_space)
        samples = self.distribution.sample(self.mc_samples, "M")

        solves = []
        i = 0.
        for s in samples.T:
            if isinstance(s, float) or isinstance(s, int):
                s = [s]

            sys.stdout.write("\rRunning Neuron: %2.1f%%" % (i/len(samples.T)*100))
            sys.stdout.flush()

            tmp_parameters = {}
            j = 0
            for parameter in parameter_name:
                tmp_parameters[parameter] = s[j]
                j += 1

            self.model.saveParameters(tmp_parameters)
            if self.model.run() == -1:
                return -1

            V = np.load("tmp_U.npy")
            t = np.load("tmp_t.npy")

            # Do a feature selection here. Make it so several feature
            # selections are performed at this step. Do this when
            # rewriting it as a class

            if feature is not None:
                V = feature(V)

            interpolation = scipy.interpolate.InterpolatedUnivariateSpline(t, V, k=3)
            solves.append((t, V, interpolation))

            i += 1

        print "\rRunning Neuron: %2.1f%%" % (i/len(samples.T)*100)

        solves = np.array(solves)
        lengths = []
        for s in solves[:, 0]:
            lengths.append(len(s))

        index_max_len = np.argmax(lengths)
        self.t = solves[index_max_len, 0]

        interpolated_solves = []
        for inter in solves[:, 2]:
            interpolated_solves.append(inter(self.t))

        self.E = (np.sum(interpolated_solves, 0).T/self.mc_samples).T
        self.Var = (np.sum((interpolated_solves - self.E)**2, 0).T/self.mc_samples).T


    def timePassed(self):
        return time.time() - self.t_start


    def singleParameters(self):
        for uncertain_parameter in self.parameters.uncertain_parameters:
            print "\rRunning for " + uncertain_parameter + "                     "

            if self.createPCExpansion(uncertain_parameter) == -1:
                print "Calculations aborted for " + uncertain_parameter
                return -1

            try:
                self.E = cp.E(self.U_hat, self.distribution)
                self.Var = cp.Var(self.U_hat, self.distribution)

                self.plotV_t(uncertain_parameter)

                samples = self.distribution.sample(self.mc_samples, "M")
                print samples.shape
                self.U_mc = self.U_hat(samples)

                self.p_05 = np.percentile(self.U_mc, 5, 1)
                self.p_95 = np.percentile(self.U_mc, 95, 1)

                self.plotConfidenceInterval(uncertain_parameter + "_confidence_interval")

            except MemoryError:
                print "Memory error, calculations aborted"
                return -1


    def allParameters(self):
        if len(self.parameters.uncertain_parameters) <= 1:
            print "Only 1 uncertain parameter"
            print "running allParameters() makes no sense"
            if self.U_hat is None:
                print "Running singleParameters() instead"
                self.singleParameters()
            return

        if self.createPCExpansion() == -1:
            print "Calculations aborted for all"
            return -1
        try:
            self.E = cp.E(self.U_hat, self.distribution)
            self.Var = cp.Var(self.U_hat, self.distribution)

            self.plotV_t("all")

            self.sensitivity = cp.Sens_t(self.U_hat, self.distribution)

            self.plotSensitivity()

            samples = self.distribution.sample(self.mc_samples, "M")

            print len(samples.shape)
            self.U_mc = self.U_hat(*samples)
            self.p_05 = np.percentile(self.U_mc, 5, 1)
            self.p_95 = np.percentile(self.U_mc, 95, 1)

            self.plotConfidenceInterval("all_confidence_interval")

            self.Corr = cp.Corr(self.P, self.distribution)

            print self.U_hat.shape
            print self.P.shape
            print self.Corr
            print self.distribution
            print
            print self.Corr.shape
            print self.t.shape
            print self.Corr[0].shape

        except MemoryError:
            print "Memory error, calculations aborted"




    def plotV_t(self, filename):
        color1 = 0
        color2 = 8

        prettyPlot(self.t, self.E, "Mean, " + filename, "time", "voltage", color1)
        plt.savefig(os.path.join(self.outputdir, filename + "_mean" + self.figureformat),
                    bbox_inches="tight")

        prettyPlot(self.t, self.Var, "Variance, " + filename, "time", "voltage", color2)
        plt.savefig(os.path.join(self.outputdir, filename + "_variance" + self.figureformat),
                    bbox_inches="tight")

        ax, tableau20 = prettyPlot(self.t, self.E, "Mean and variance, " + filename,
                                   "time", "voltage, mean", color1)
        ax2 = ax.twinx()
        ax2.tick_params(axis="y", which="both", right="on", left="off", labelright="on",
                        color=tableau20[color2], labelcolor=tableau20[color2], labelsize=14)
        ax2.set_ylabel('voltage, variance', color=tableau20[color2], fontsize=16)
        ax.spines["right"].set_edgecolor(tableau20[color2])

        ax2.set_xlim([min(self.t), max(self.t)])
        ax2.set_ylim([min(self.Var), max(self.Var)])

        ax2.plot(self.t, self.Var, color=tableau20[color2], linewidth=2, antialiased=True)

        ax.tick_params(axis="y", color=tableau20[color1], labelcolor=tableau20[color1])
        ax.set_ylabel('voltage, mean', color=tableau20[color1], fontsize=16)
        ax.spines["left"].set_edgecolor(tableau20[color1])
        plt.tight_layout()
        plt.savefig(os.path.join(self.outputdir,
                    filename + "_variance_mean" + self.figureformat),
                    bbox_inches="tight")

        plt.close()

    def plotConfidenceInterval(self, filename):

        ax, color = prettyPlot(self.t, self.E, "Confidence interval", "time", "voltage", 0)
        plt.fill_between(self.t, self.p_05, self.p_95, alpha=0.2, facecolor=color[8])
        prettyPlot(self.t, self.p_95, color=8, new_figure=False)
        prettyPlot(self.t, self.p_05, color=9, new_figure=False)
        prettyPlot(self.t, self.E, "Confidence interval", "time", "voltage", 0, False)

        plt.ylim([min([min(self.p_95), min(self.p_05), min(self.E)]),
                  max([max(self.p_95), max(self.p_05), max(self.E)])])

        plt.legend(["Mean", "$P_{95}$", "$P_{5}$"])
        plt.savefig(os.path.join(self.outputdir, filename + self.figureformat),
                    bbox_inches="tight")

        plt.close()

    def plotSensitivity(self):
        parameter_names = self.parameters.getUncertain("name")

        for i in range(len(self.sensitivity)):
            prettyPlot(self.t, self.sensitivity[i],
                       parameter_names[i] + " sensitivity", "time",
                       "sensitivity", i, True)
            plt.title(parameter_names[i] + " sensitivity")
            plt.ylim([0, 1.05])
            plt.savefig(os.path.join(self.outputdir,
                                     parameter_names[i] +
                                     "_sensitivity" + self.figureformat),
                        bbox_inches="tight")
        plt.close()

        for i in range(len(self.sensitivity)):
            prettyPlot(self.t, self.sensitivity[i], "sensitivity", "time",
                       "sensitivity", i, False)

        plt.ylim([0, 1.05])
        plt.xlim([self.t[0], 1.3*self.t[-1]])
        plt.legend(parameter_names)
        plt.savefig(os.path.join(self.outputdir, "all_sensitivity" + self.figureformat),
                    bbox_inches="tight")




if __name__ == "__main__":

    modelfile = "INmodel.hoc"
    modelpath = "neuron_models/dLGN_modelDB/"
    parameterfile = "Parameters.hoc"

    original_parameters = {
        "rall": 113,       # Taken from litterature
        "cap": 1.1,        #
        "Rm": 22000,       # Estimated by hand
        "Vrest": -63,      # Experimentally measured
        "Epas": -67,       # Estimated by hand
        "gna": 0.09,
        "nash": -52.6,
        "gkdr": 0.37,
        "kdrsh": -51.2,
        "gahp": 6.4e-5,
        "gcat": 1.17e-5,    # Estimated by hand
        "gcal": 0.0009,
        "ghbar": 0.00011,   # Estimated by hand
        "catau": 50,
        "gcanbar": 2e-8
    }


    fitted_parameters = ["Rm", "Epas", "gkdr", "kdrsh", "gahp", "gcat", "gcal",
                         "ghbar", "catau", "gcanbar"]



    test_parameters = ["Rm", "Epas", "gkdr", "kdrsh", "gahp", "gcat"]

    distribution_function = Distribution(0.1).uniform
    distribution_functions = {"Rm": distribution_function, "Epas": distribution_function}

    #test_parameters = "Rm"
    test_parameters = ["Rm", "Epas"]
    memory_report = Memory()
    parameters = Parameters(original_parameters, distribution_function, test_parameters)
    #parameters = Parameters(original_parameters, distribution_function, fitted_parameters)

    model = Model(modelfile, modelpath, parameterfile, original_parameters, memory_report)
    test = UncertaintyEstimation(model, parameters, "figures/test")

    # t1 = test.timePassed()
    # test.pseudoMC("Rm")
    # test.plotV_t("MC")
    # t2 = test.timePassed()
    # test.singleParameters()
    # t3 = test.timePassed()
    # print "MC ", t2-t1
    # print "PC ", t3-t2

#    test.singleParameters()
    test.allParameters()

    #test_distributions = {"uniform": [0.05]}
    #exploration = UncertaintyEstimations(model, fitted_parameters, test_distributions)
    #exploration.exploreParameters()

    #distributions = {"uniform": np.linspace(0.01, 0.1, 10), "normal": np.linspace(0.01, 0.1, 10)}
    #exploration = UncertaintyEstimations(model, fitted_parameters, distributions)
    #exploration.exploreParameters()



    subprocess.Popen(["play", "-q", "ship_bell.wav"])
    print "The total runtime is: " + str(datetime.timedelta(seconds=(test.timePassed())))
