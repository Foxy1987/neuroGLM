import numpy as np
from scipy.linalg import toeplitz, hankel
from scipy import stats, signal
from basisFactory.bases import Basis, RaisedCosine



class Regressor:
	def __int__(self, basis_):
		name = None
		params = []
		basis_ = None
		self.edim_ = 0

	def duration(self, *args, **kwargs):
		pass

	@property
	def edim(self):
		return self.edim_

	def conv_basis(self, s, bases):
		'''
		Computes the convolutions of X with the selected basis functions
		:param X: has to be an nt, nx ndarray!
		:param bases:
		:return:
		'''
		slen = len(s)
		tb, nkt = bases.shape

		Xstim = np.zeros((slen, nkt))
		# convolve the stim with each column of the basis matrix
		for i in range(nkt):
			Xstim[:, i] = self.sameconv(s, bases[:, i])
		return Xstim

	def sameconv(self, x, f):
		x = np.asarray([x.T])
		f = np.asarray([f.T])
		[xwid, nx] = x.shape
		[fwid, nf] = f.shape
		a = np.concatenate((np.zeros(nf - 1), x), axis=None)
		b = np.rot90(f, k=2)
		res = signal.convolve2d(np.asarray([a]), b, mode='valid')
		return res.squeeze()

	def spikefilt(self, sps, basis):
		nt, nb = basis.shape
		slen = len(sps)
		sps_ = np.asarray([sps])

		# Do convolution and remove extra bins
		res = signal.convolve2d(sps_.T, basis, mode='full')
		Xsp = np.vstack((np.zeros((1, nb)), res[:-nt, :]))
		return Xsp


class RegressorPoint(Regressor):
	def __init__(self, name, bins_after, bins_before=0):
		self.name = name
		self.bins_after = bins_after
		self.bins_before = bins_before
		self.params = [name + "_time"]

	def duration(self, **kwargs):
		return self.bins_after + self.bins_before

	def matrix(self, params, n_bins, _times, _bintimes, **kwargs):
		time = params[self.name + "_time"]
		M = np.zeros((n_bins, self.bins_before))

		# get the index of the first bin greater than time
		index = next(i for i in range(0, len(_times)) if _bintimes[i] <= time and _bintimes[i + 1] > time)

		M[(range(index - self.bins_before, index),
		   range(0, self.bins_before))] = 1

		return np.fliplr(M)


class RegressorContinuous(Regressor):
	def __init__(self, name, bins_before, bins_after=0, basis=None):
		self.name = name
		self.bins_after = bins_after
		self.bins_before = bins_before
		self.params = [name + "_time"]

		# set super class parameters: every regressor may have a basis (or not)
		# and associated with it is a dimension
		self.basis = basis
		self.edim_ = basis.nbases

	def duration(self, **kwargs):
		return self.bins_before + self.bins_after

	def matrix(self, params, n_bins, _times, _bintimes, **kwargs):
		time = params[self.name + "_time"]  # time is the time the regressor appears during the trial
		# Xdsgn = np.zeros((n_bins, self.bins_before))
		# index = next(i for i in range(0, len(_times)) if _bintimes[i] <= time and _bintimes[i + 1] > time)

		stim = params[self.name + "_val"]

		if self.basis:
			paddedstim2 = np.hstack((np.zeros(1), stim))
			print("convolving padded stimulus with raised cosine basis functions")
			# convolve stimulus with bases functions
			Xdsgn2 = self.conv_basis(paddedstim2, self.basis.B)
			Xdsgn2 = Xdsgn2[:-1, :]
		else:
			paddedstim2 = np.hstack((np.zeros(self.bins_before - 1), stim))
			Xdsgn2 = hankel(paddedstim2[:(-self.bins_before + 1)], stim[(-self.bins_before):])

		return Xdsgn2


class RegressorSphist(Regressor):
	def __init__(self, name, bins_before, bins_after=0, basis=None):
		self.name = name
		self.bins_after = bins_after
		self.bins_before = bins_before
		self.params = [name + "_time"]

		# set super class parameters: every regressor may have a basis (or not)
		# and associated with it is a dimension
		self.basis = basis
		self.edim_ = basis.nbases

	def duration(self, **kwargs):
		return self.bins_before + self.bins_after

	def matrix(self, params, n_bins, _times, _bintimes, **kwargs):
		time = params[self.name + "_time"]  # time is the time the regressor appears during the trial

		stim = params[self.name + "_val"]

		if self.basis:
			# paddedstim2 = np.hstack((np.zeros(1), stim))
			print("convolving padded stimulus with raised cosine basis functions")
			# convolve stimulus with bases functions
			Xdsgn2 = self.spikefilt(stim, self.basis.B)
			#Xdsgn2 = Xdsgn2[:-1, :]
		else:
			paddedstim2 = np.hstack((np.zeros(self.bins_before), stim[:-1])) # everything except the current spike at this time step
			Xdsgn2 = hankel(paddedstim2[:-self.bins_before + 1], paddedstim2[(-self.bins_before):])

		return Xdsgn2



class DesignMatrix:
	def __init__(self, dt=0.001, mintime=-1000, maxtime=1000):
		self._dt = dt
		self._mintime = mintime  # in sec
		self._maxtime = maxtime  # in sec
		self._times = np.arange(mintime, maxtime - dt / 2, dt) + dt / 2
		self._bintimes = np.append(self._times - dt / 2, self._times[-1] + dt / 2)
		self._regressors = []

	def bin_spikes(self, spikes):
		"""
		convert spike times into spike counts
		:param spikes: indices of spikes
		:return: binned spike count
		"""
		return np.histogram(spikes, self._bintimes)[0]

	def empty_matrix(self):
		# n_regressor_timepoints = sum([r.duration() for r in self._regressors])
		# return np.zeros((0, int(n_regressor_timepoints)))  # this initializes number of column using nfilt
		edim = sum([r.edim for r in self._regressors])
		return np.zeros((0, int(edim)))  # this initializes number of column using nfilt

	def n_bins(self):
		return int((self._maxtime - self._mintime) / self._dt)

	def add_regressor(self, regressor):
		self._regressors.append(regressor)

	def build_matrix(self, params=dict(), trial_end=None):
		M = np.zeros((self.n_bins(), 0))  # initialize a matrix with nbins rows and intially 0 columns
		for r in self._regressors:

			Mr = r.matrix(params=params, n_bins=self.n_bins(), _times=self._times, _bintimes=self._bintimes, \
						  trial_end=trial_end)

			M = np.concatenate([M, Mr], axis=1)

		return M

	def get_regressor_from_output(self, output):
		'''

		:param name:
		:param output:
		:return: dictionary containing filter for each regressor
		'''

		d = {}
		start_index = 1 # start from 1 to ignore bias
		for r in self._regressors:
			name = r.name

			out = output[start_index:start_index + r.edim]

			if r.basis:
				y = (r.basis.B * out.T).sum(axis=1) 		# sum across the weights on each basis vector

				if r.name == 'stim':
					x = np.asarray(range(-len(y), 0))
				else:
					x = np.asarray(range(0, len(y)))
				d[name] = (x, y)
				start_index += r.edim
			else:
				y = output[start_index:start_index + r.bins_before]
				x = np.asarray(range(-r.bins_before, r.bins_after)) * self._dt

		return d

	def get_regressor_from_dm(self, name, output):
		start_index = 0
		for r in self._regressors:
			if r.name == name:
				break
			start_index += r.duration(n_bins=self.n_bins())
		r_length = r.duration(n_bins=self.n_bins())
		dm = output[:, start_index:start_index + r_length]

		return dm







class Experiment:
	"""
	class to hold
	"""
	def __init__(self, dtSp, duration, stim=None, sptimes=None):
		self._regressortype = {}
		self._sptimes = sptimes
		self._stim = stim

		self.duration = duration
		# to get the appropriate regressor, we would call dspec.expt.trial[regressor.name]
		# for this to work, regressor must have the name of either 'sptrain' or 'stim'
		# check what Pillow does
		self.trial = {}

		self._dtSp = dtSp
		#self._dtStim = dtStim
		# self.duration = len(stim) * dtSp

	def register_spike_train(self, label):
		# we initialize Experiment object with sptrain and stim
		# registering adds internal/external regressors to a dictionary to be processed
		# not every analysis may use all available regressors
		self.trial['sptrain'] = self.sptimes
		self._regressortype['sptrain'] = label # check this label, probably sptrain needs to be the value not the key

	def registerContinuous(self, label):
		self.trial['stim'] = self._stim
		self._regressortype['stim'] = label

	@property
	def regressortype(self):
		return self._regressortype

	@property
	def dtStim(self):
		return self._dtStim

	@property
	def dtSp(self):
		return self._dtSp

	@property
	def stim(self):
		return self._stim

	@property
	def sptimes(self):
		return self._sptimes


class DesignSpec:
	def __init__(self, expt: Experiment, trialinds: list):
		self.expt = expt
		self._trialinds = trialinds

		self.dt_ = expt.dtSp
		self._ntfilt = 1000
		self._ntsphist = 100

		self.regressors = []

	def addRegressorSpTrain(self):

		# first make basis to represent the spike history filter
		basis = RaisedCosine(100, 8, 1, 'sphist')
		# should dt be 1 if sptrain is binned
		#basis.makeNonlinearRaisedCos(self.expt.dtSp, [0, 100], 1)

		basis.makeNonlinearRaisedCosPostSpike(self.expt.dtSp, [0.001, 1], 0.05)

		# when the regressor is made with a basis object, then when the matrix func is called,
		# a matrix will be created by convolving the stimulus (sptrain) with the basis functions
		r = RegressorSphist(self.expt.regressortype['sptrain'], self._ntsphist, basis=basis)
		self.regressors.append(r)

	def addRegressorContinuous(self):
		# make basis to represent stim filter
		basis = RaisedCosine(100, 5, 1, 'stim')

		basis.makeNonlinearRaisedCosStim(self.expt.dtSp, [1, 400], 10, self._ntfilt)
		r = RegressorContinuous(self.expt.regressortype['stim'], self._ntfilt, basis=basis)
		self.regressors.append(r)


	def compileDesignMatrixFromTrialIndices(self):
		expt = self.expt
		dt = self.dt_

		# need to fix so i can use dt = 1
		#totalT = np.ceil(expt.duration/ expt.dtSp)
		totalT = expt.duration

		dm = DesignMatrix(dt, 0, totalT)
		for k in self.regressors:
			dm.add_regressor(k)

		Xfull = dm.empty_matrix()
		Yfull = np.asarray([])

		for tr in self._trialinds:
			# nT = np.ceil(expt.duration / expt.dtSp)

			# build param dict to pass to dm.buildMatrix(), which contains time that regressor cares about
			# and the regressor values themselves
			d = {}
			for kregressor in self.regressors:

				# gets the stimulus based on the regressor name, the regressor name
				# must match the field in the experiment object
				name = kregressor.name
				stim = self.expt.trial[name][tr]

				print('forming design matrix from trial indices')
				# binned_spikes = dm.bin_spikes(self.expt.trial['sptrain'][tr])
				d[name + '_time'] = 0  # this time could be used to fetch that part of the stimulus but not really used right now
				d[name + '_val'] = stim

			X = dm.build_matrix(d)

			Xfull = np.concatenate([Xfull, X], axis=0)
			Yfull = np.concatenate([Yfull, stim])

		# Xfull = stats.zscore(Xfull)
		# Xfull = np.column_stack([np.ones_like(Yfull), Xfull])

		return dm, Xfull, Yfull



	@property
	def stim(self):
		return self._stim

	@property
	def ntfilt(self):
		return self._ntfilt

	@property
	def ntsphist(self):
		return self._ntsphist

	@property
	def dt(self):
		return self.dt_


