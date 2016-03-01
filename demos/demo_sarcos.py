#! /usr/bin/env python3
""" A La Carte GP Application to SARCOS dataset. """

import logging
import numpy as np
import revrand.legacygp as gp
import revrand.legacygp.kernels as kern

from revrand import regression, glm, basis_functions, likelihoods
from revrand.validation import smse, msll
from revrand.utils.datasets import fetch_gpml_sarcos_data

#
# Settings
#

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

lenscale = 10
sigma = 100
noise = 1
regulariser = 1
nbases = 300
gp_Ntrain = 1024
passes = 10
rate = 0.9
eta = 1e-6
batchsize = 100
rank = 0

useSGD = True
diagcov = True


#
# Load data
#

gpml_sarcos = fetch_gpml_sarcos_data()

X_train = gpml_sarcos.train.data
y_train = gpml_sarcos.train.targets

X_test = gpml_sarcos.test.data
y_test = gpml_sarcos.test.targets

Ntrain, D = X_train.shape


# Get random subset of data for training the GP
train_ind = np.random.choice(range(Ntrain), size=gp_Ntrain, replace=False)
X_train_sub = X_train[train_ind, :]
y_train_sub = y_train[train_ind]


#
# Train A la Carte
#

base = basis_functions.RandomRBF_ARD(nbases, D)
lenARD = lenscale * np.ones(D)

if useSGD:
    log.info("Using SGD regressor")
    # params = regression.learn_sgd(X_train, y_train, base, lenARD,
    #                               rate=rate, var=noise**2, rank=rank,
    #                               regulariser=regulariser, eta=eta,
    #                               passes=passes, batchsize=batchsize)
    llhood = likelihoods.Gaussian()
    lparams = [noise**2]
    params = glm.learn(X_train, y_train, llhood, lparams, base, lenARD,
                       postcomp=5, reg=regulariser, use_sgd=True, rate=rate,
                       eta=eta, batchsize=batchsize, maxit=passes)
else:
    log.info("Using full variational regressor")
    params = regression.learn(X_train, y_train, base, lenARD,
                              var=noise**2, diagcov=diagcov,
                              regulariser=regulariser)


#
# Train GP
#


def kdef(h, k):
    return (h(1e-5, 1., 0.5)
            * k(kern.gaussian, [h(1e-5, 1e5, l) for l in lenARD])
            + k(kern.lognoise, h(-4, 1, -3)))

hyper_params = gp.learn(X_train_sub, y_train_sub, kdef, verbose=True,
                        ftol=1e-15, maxiter=1000)


#
# Predict Revrand
#

# Ey, Vf, Vy = regression.predict(X_test, base, *params)
# Sy = np.sqrt(Vy)
Ey, Vf, _, _ = glm.predict_meanvar(X_test, llhood, base, *params)
Vy = Vf + params[2][0]
Sy = np.sqrt(Vy)


#
# Predict GP
#

regressor = gp.condition(X_train_sub, y_train_sub, kdef, hyper_params)
query = gp.query(regressor, X_test)
Ey_gp = gp.mean(query)
Vf_gp = gp.variance(query)
Vy_gp = gp.variance(query, noise=True)
Sy_gp = np.sqrt(Vy_gp)


#
# Validation
#

log.info("Subset GP smse = {}, msll = {},\n\thypers = {}, noise = {}."
         .format(smse(y_test, Ey_gp), msll(y_test, Ey_gp, Vy_gp, y_train),
                 hyper_params[0], hyper_params[1]))
log.info("Revrand smse = {}, msll = {},\n\thypers = {}, noise = {}."
         .format(smse(y_test, Ey), msll(y_test, Ey, Vy, y_train),
                 params[2], np.sqrt(params[3])))
