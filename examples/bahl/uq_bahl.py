import uncertainpy as un
import chaospy as cp

from bahl import NeuronModelBahl

parameterlist = [["e_pas", -80, cp.Uniform(-60, -85)],
                 ["apical Ra", 261, cp.Uniform(150, 300)]]

# model = un.NeuronModel(path="bahl_neuron_model", name="bahl",
#                        stimulus_start=100, stimulus_end=600)

model = NeuronModelBahl(stimulus_start=100, stimulus_end=600)


features = un.SpikingFeatures()

uncertainty = un.UncertaintyEstimation(model=model,
                                       parameters=parameterlist,
                                       features=features,
                                       save_figures=True)

uncertainty.uncertainty_quantification(plot_condensed=False,
                                       plot_results=True)
uncertainty.uncertainty_quantification(single=True,
                                       plot_results=False)
