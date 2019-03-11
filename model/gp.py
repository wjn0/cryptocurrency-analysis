import numpy as np
import emcee

class GaussianProcess(object):
    def __init__(self, kernel, nwalkers, tau_prior_mean, tau_prior_var,
                 sig_var_prior_alpha, sig_var_prior_beta, num_taus=1):
        """
        Basic Gaussian process model which allows for Bayesian estimation of the
        scale and signal variance parameters.

        kernel: The kernel function to use.
        nwalkers: The number of walkers to use when fitting the MCMC model.
        tau_prior_mean: The prior mean for tau (LogNormal).
        tau_prior_mean: The prior variance for tau (LogNormal).
        sig_var_prior_alpha: The prior alpha parameter for Beta signal variance.
        sig_var_prior_beta: The prior beta parameter for Beta signal variance.
        """
        self.parameters = {
            'KERNEL': kernel,
            'NWALKERS': nwalkers,
            'TAU_PRIOR_MEAN': tau_prior_mean,
            'TAU_PRIOR_VAR': tau_prior_var,
            'SIG_VAR_PRIOR_ALPHA': sig_var_prior_alpha,
            'SIG_VAR_PRIOR_BETA': sig_var_prior_beta
	}
        self.num_params = num_taus + 1

    def _construct_kernel(self, params, times):
        """
        Construct the kernel matrix for a given input set.

        times: The inputs to the kernel construction, of length T.
        tau: The scale parameter to be passed to the kernel function.
        sig_var: The signal variance.

        Returns a T x T kernel matrix constructed accordingly.
        """
        k = self.parameters['KERNEL']
        sig_var = params[-1]
        params = params[:-1]

        T = len(times)
        K = np.eye(T)
        for t1 in range(T):
            for t2 in range(t1, T):
                if t1 != t2:
                    el = sig_var * k(times[t1], times[t2], params)
                    K[t1, t2] = el
                    K[t2, t1] = el

        return K

    def likelihood(self, params):
        tau_mean = self.parameters['TAU_PRIOR_MEAN']
        tau_var = self.parameters['TAU_PRIOR_VAR']
        sig_alpha = self.parameters['SIG_VAR_PRIOR_ALPHA']
        sig_beta = self.parameters['SIG_VAR_PRIOR_BETA']

        sig_var = params[-1]
        taus = params[:-1]

        if (taus > 0).all() and sig_var < 1 and sig_var > 0:
            K = self._construct_kernel(params, range(len(self.data)))
            Kinv = np.linalg.inv(K)

            loglik = -0.5 * np.matmul(self.data, np.matmul(Kinv, self.data))
            logtauprior = np.sum(
                np.log(1/taus) - 0.5*(np.log(taus) - tau_mean)**2/tau_var
            )
            logsigprior = np.log(sig_var**(sig_alpha - 1)) + np.log((1 - sig_var)**(sig_beta - 1))

            return loglik + logtauprior + logsigprior
        else:
            return -np.inf


    def fit(self, data, init=None, numit=500):
        """
        Estimate the model parameters using a dataset.

        data: The dataset, of size T, where T is the number of timepoints.
        numit: The number of MCMC iterations to run.

        Returns the MCMC chain.
        """
        tau_mean = self.parameters['TAU_PRIOR_MEAN']
        tau_var = self.parameters['TAU_PRIOR_VAR']
        sig_alpha = self.parameters['SIG_VAR_PRIOR_ALPHA']
        sig_beta = self.parameters['SIG_VAR_PRIOR_BETA']
        nwalkers = self.parameters['NWALKERS']

        self.data = data

        if not init:
            if self.num_params > 2:
                init = [
                    np.concatenate((
                        [np.random.lognormal(tau_mean, tau_var) for _ in range(self.num_params - 1)],
                        [np.random.beta(sig_alpha, sig_beta)]
                    )) for _ in range(nwalkers)
                ]
            else:
                init = [
                    [np.random.lognormal(tau_mean, tau_var),
                     np.random.beta(sig_alpha, sig_beta)] for _ in range(nwalkers)
                ]

        sampler = emcee.EnsembleSampler(nwalkers, self.num_params, self.likelihood)
        ret = sampler.run_mcmc(init, numit)
        self.chain = sampler.chain
        self.terminals = ret[0]
        self.likelihoods = ret[1]
         
        return self.chain

    def optimal_params(self, burnin=100):
        """
        Gets the optimal parameters of the model.
        """
        return np.mean(self.chain[:, burnin:, :].reshape(-1, self.chain.shape[2]), axis=0)

    def predict_next_timepoint(self):
        """
        Predicts the value of the function at the next timepoint.

        burnin: The number of samples to consider burn-in.

        Returns the predicted function value at T + 1, where T is the number of
        training timepoints.
        """
        params = self.optimal_params()
        T = len(self.data)
        K = self._construct_kernel(params, range(T + 1))

        return np.matmul(K[:T, T], np.matmul(np.linalg.inv(K[:T, :T]), self.data))

