import uncertainpy as un
import chaospy as cp

from coffee_cup_class import CoffeeCup

T_env_dist = cp.Uniform(15, 25)
kappa_dist = cp.Uniform(-0.075, -0.025)

parameterlist = [["kappa", -0.05, kappa_dist],
                 ["T_env", 20, T_env_dist]]

parameters = un.Parameters(parameterlist)
model = CoffeeCup()

uncertainty = un.UncertaintyEstimation(model=model,
                                       parameters=parameters,
                                       features=None)

uncertainty.uncertainty_quantification(plot_condensed=False)