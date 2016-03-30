#!/bin/env python

import iemgmm
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import matplotlib.lines as lines
import datetime
from functools import partial

def plotResults(orig, data, gmm, patch=None):
    fig = plt.figure(figsize=(6,6))
    ax = fig.add_subplot(111, aspect='equal')

    # plot inner and outer points
    ax.plot(orig[:,0], orig[:,1], 'o', mfc='r', mec='None')
    ax.plot(data[:,0], data[:,1], 'o', mfc='b', mec='None')

    # prediction
    B = 100
    x,y = np.meshgrid(np.linspace(-5,15,B), np.linspace(-5,15,B))
    coords = np.dstack((x.flatten(), y.flatten()))[0]

    # compute sum_k(p_k(x)) for all x
    p = gmm(coords).reshape((B,B))
    # for better visibility use arcshinh stretch
    p = np.arcsinh(p/1e-4)
    cs = ax.contourf(p, 10, extent=(-5,15,-5,15), cmap=plt.cm.Greys)
    for c in cs.collections:
        c.set_edgecolor(c.get_facecolor())

    # plot boundary
    if patch is not None:
        import copy
        if hasattr(patch, '__iter__'):
            for p in patch:
                ax.add_artist(copy.copy(p))
        else:
            ax.add_artist(copy.copy(patch))

    # add complete data logL to plot
    logL = gmm(orig, as_log=True).mean()
    ax.text(0.05, 0.95, '$\log{\mathcal{L}} = %.3f$' % logL, ha='left', va='top', transform=ax.transAxes)

    ax.set_xlim(-5, 15)
    ax.set_ylim(-5, 15)
    ax.set_xticks([])
    ax.set_yticks([])
    plt.tight_layout()
    plt.show()

def getBox(coords):
    box_limits = np.array([[0,0],[10,10]])
    return (coords[:,0] > box_limits[0,0]) & (coords[:,0] < box_limits[1,0]) & (coords[:,1] > box_limits[0,1]) & (coords[:,1] < box_limits[1,1])

def getHole(coords):
    x,y,r = 6.5, 6., 2
    return ((coords[:,0] - x)**2 + (coords[:,1] - y)**2 > r**2)

def getBoxWithHole(coords):
    return getBox(coords)*getHole(coords)

def getHalfDensity(coords, rng=np.random):
    mask = np.ones(coords.shape[0], dtype='bool')
    mask[rng.rand(coords.shape[0]) < 0.5] = 0
    return mask

def getTaperedDensity(coords, rng=np.random):
    mask = np.ones(coords.shape[0], dtype='bool')
    mask[rng.rand(coords.shape[0]) < coords[:,0]/8] = 0
    return mask

def getCut(coords):
    return (coords[:,0] < 5)

def getSelection(type="hole", rng=np.random):
    if type == "hole":
        cb = getHole
        ps = patches.Circle([6.5, 6.], radius=2, fc="none", ec='b', ls='dotted')
    if type == "box":
        cb = getBox
        ps = patches.Rectangle([0,0], 10, 10, fc="none", ec='b', ls='dotted')
    if type == "boxWithHole":
        cb = getBoxWithHole
        ps = [patches.Circle([6.5, 6.], radius=2, fc="none", ec='b', ls='dotted'),
            patches.Rectangle([0,0], 10, 10, fc="none", ec='b', ls='dotted')]
    if type == "cut":
        cb = getCut
        ps = lines.Line2D([5, 5],[-5, 15], ls='dotted', color='b')
    if type == "tapered":
        cb = partial(getTaperedDensity, rng=rng)
        ps = lines.Line2D([8, 8],[-5, 15], ls='dotted', color='b')
    return cb, ps


if __name__ == '__main__':

    # set up RNG
    seed = 42
    from numpy.random import RandomState
    rng = RandomState(seed)
    verbose = False

    # draw N points from 3-component GMM
    N = 400
    D = 2
    gmm = iemgmm.GMM(K=3, D=2)
    gmm.amp[:] = np.array([ 0.36060026,  0.27986906,  0.206774])
    gmm.amp /= gmm.amp.sum()
    gmm.mean[:,:] = np.array([[ 0.08016886,  0.21300697],
                              [ 0.70306351,  0.6709532 ],
                              [ 0.01087670,  0.852077]])*10
    gmm.covar[:,:,:] = np.array([[[ 0.08530014, -0.00314178],
                                  [-0.00314178,  0.00541106]],
                                 [[ 0.03053402, 0.0125736],
                                  [0.0125736,  0.01075791]],
                                 [[ 0.00258605,  0.00409287],
                                 [ 0.00409287,  0.01065186]]])*100

    orig = gmm.draw(N, rng=rng)


    # get observational selection function
    cb, ps = getSelection("hole", rng=rng)

    # add isotropic errors on data
    disp = 0.8
    noisy = orig + rng.normal(0, scale=disp, size=(len(orig), D))
    # apply selection
    sel = cb(noisy)
    data = iemgmm.createShared(noisy[sel])
    covar = iemgmm.createShared(np.tile(disp**2 * np.eye(D), (len(data), 1, 1)))

    # make sure that the initial placement of the components
    # uses the same RNG for comparison
    init_cb = partial(iemgmm.initializeFromDataMinMax, rng=rng)

    # repeated runs: store results and logL
    K = 3
    R = 10
    imp = iemgmm.GMM(K=K*R, D=D)

    # 1) IEMGMM without imputation, ignoring errors
    start = datetime.datetime.now()
    rng = RandomState(seed)
    for r in xrange(R):
        imp_ = iemgmm.fit(data, K=K, w=0.1, init_callback=init_cb, cutoff=5, verbose=verbose)
        ll = imp_.logL(data).mean()
        imp.amp[r*K:(r+1)*K] = imp_.amp * np.exp(ll)
        imp.mean[r*K:(r+1)*K,:] = imp_.mean
        imp.covar[r*K:(r+1)*K,:,:] = imp_.covar
    imp.amp /= imp.amp.sum()
    print "execution time %ds" % (datetime.datetime.now() - start).seconds
    plotResults(orig, data, imp, patch=ps)

    # 2) IEMGMM without imputation, incorporating errors
    start = datetime.datetime.now()
    rng = RandomState(seed)
    for r in xrange(R):
        imp_ = iemgmm.fit(data, covar=covar, K=K, w=0.1, init_callback=init_cb, cutoff=5, verbose=verbose)
        ll = imp_.logL(data).mean()
        imp.amp[r*K:(r+1)*K] = imp_.amp * np.exp(ll)
        imp.mean[r*K:(r+1)*K,:] = imp_.mean
        imp.covar[r*K:(r+1)*K,:,:] = imp_.covar
    imp.amp /= imp.amp.sum()
    print "execution time %ds" % (datetime.datetime.now() - start).seconds
    plotResults(orig, data, imp, patch=ps)

    # 3) IEMGMM with imputation, igoring errors
    start = datetime.datetime.now()
    rng = RandomState(seed)
    for r in xrange(R):
        imp_ = iemgmm.fit(data, K=K, w=0.1, init_callback=init_cb, cutoff=5, sel_callback=cb, verbose=verbose)
        ll = imp_.logL(data).mean()
        imp.amp[r*K:(r+1)*K] = imp_.amp * np.exp(ll)
        imp.mean[r*K:(r+1)*K,:] = imp_.mean
        imp.covar[r*K:(r+1)*K,:,:] = imp_.covar
    imp.amp /= imp.amp.sum()
    print "execution time %ds" % (datetime.datetime.now() - start).seconds
    plotResults(orig, data, imp, patch=ps)

    # 4) IEMGMM with imputation, incorporating errors
    start = datetime.datetime.now()
    rng = RandomState(seed)
    for r in xrange(R):
        imp_ = iemgmm.fit(data, covar=covar, K=K, w=0.1, init_callback=init_cb, cutoff=5, sel_callback=cb, verbose=verbose)
        ll = imp_.logL(data).mean()
        imp.amp[r*K:(r+1)*K] = imp_.amp * np.exp(ll)
        imp.mean[r*K:(r+1)*K,:] = imp_.mean
        imp.covar[r*K:(r+1)*K,:,:] = imp_.covar
    imp.amp /= imp.amp.sum()
    print "execution time %ds" % (datetime.datetime.now() - start).seconds
    plotResults(orig, data, imp, patch=ps)
