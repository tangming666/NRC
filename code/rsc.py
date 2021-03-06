#!/usr/bin/env python
# coding: utf-8

import numpy as np
from numpy import load
from math import exp
import math
from scipy import optimize
import cvxpy as cvx
from scipy.sparse.linalg import cg, LinearOperator
from numpy.linalg import norm


def l1ls(A, y, lmbda, x0=None, At=None, m=None, n=None, tar_gap=1e-3,
         quiet=False, eta=1e-3, pcgmaxi=5000):
    """
    Solve a l1-Regularized Least Squares problem.

    l1_ls solves problems of the following form:

        minimize ||A*x-y||^2 + lambda*sum|x_i|,

    where A and y are problem data and x is variable (described below).

    Parameters
    ----------
    A : mxn matrix
        input data. Columns correspond to features. Pass sparse matrixes in CSR
        format for best performance.
    y : m vector
        outcome.
    lmbda : positive float
        regularization parameter.
    x0: ndarray
        initial guess of the solution
    At : nxm matrix, optional
        transpose of A.
    m : int, optional
        number of examples (rows) of A.
    n : int, optional
        number of features (column)s of A.
    tar_gap : float, optional
        relative target duality gap (default: 1e-3).
    quiet : boolean, optional
        suppress printing message when true (default: False).
    eta : float, optional
        parameter for PCG termination (default: 1e-3).
    pcgmaxi : int, optional
        number of maximum PCG iterations (default: 5000).

    Returns
    -------
    x : array_like
        classifier.
    status  : string
        'Solved' or 'Failed'
    history : matrix
        history data. Columns represent (truncated) Newton iterations; rows
        represent the following:
             - 1st row) gap
             - 2nd row) primal objective
             - 3rd row) dual objective
             - 4th row) step size
             - 5th row) pcg status flag (-1 = error, 1 = failed, 0 = success)

    References
    ----------
    * S.-J. Kim, K. Koh, M. Lustig, S. Boyd, and D. Gorinevsky. An
      Interior-Point Method for Large-Scale l1-Regularized Least Squares,
      (2007), IEEE Journal on Selected Topics in Signal Processing,
      1(4):606-617.
    """
    At = A.transpose() if At is None else At
    m = A.shape[0] if m is None else m
    n = A.shape[1] if n is None else n

    # Interior Point Method parameters
    MU = 2             # updating parameter of t
    MAX_NT_ITER = 400  # maximum number of IPM (Newton) iterations

    # Line search parameters
    ALPHA = 0.01       # minimum fraction of decrease in the objective
    BETA = 0.5         # stepsize decrease factor
    MAX_LS_ITER = 100  # maximum backtracking line search iteration

    t0 = min(max(1, 1/lmbda), 2 * n / 1e-3)

    x = np.zeros(n) if x0 is None else x0.ravel()
    y = y.ravel()
    status, history = 'Failed', []

    u = np.ones(n)
    t = t0
    reltol = tar_gap

    f = np.hstack((x - u, - x - u))

    # Result/History variables
    pobjs, dobjs, sts, pflgs = [], [], [], []
    pobj, dobj, s, pflg = np.inf, -np.inf, np.inf, 0

    ntiter, lsiter = 0, 0
    normg = 0
    dxu = np.zeros(2*n)

    # This can be slow, so instead, we use a cruder preconditioning
    # diagxtx = diag(At.dot(A))
    diagxtx = 2 * np.ones(n)

    #if not quiet:
    #    print('\nSolving a problem of size (m={}, n={})'
    #          ', with lambda={:5e}'.format(m, n, lmbda))
    #    print('----------------------------------------'
    #          '------------------------------')
    #    print('{:>5s} {:>9s} {:>15s} {:>15s} {:>13s}'
    #          .format('iter', 'gap', 'primobj', 'dualobj',
    #                  'step len'))

    for ntiter in range(0, MAX_NT_ITER):
        z = A.dot(x) - y

        # Calculating the duality gap
        nu = 2 * z

        maxAnu = norm(At.dot(nu), np.inf)
        if maxAnu > lmbda:
            nu = nu * lmbda / maxAnu

        pobj = z.dot(z) + lmbda*norm(x, 1)
        dobj = max(-0.25 * nu.dot(nu) - nu.dot(y), dobj)
        gap = pobj - dobj

        pobjs.append(pobj)
        dobjs.append(dobj)
        sts.append(s)
        pflgs.append(pflg)

        # Stopping criterion
        #if not quiet:
        #    print('{:4d} {:12.2e} {:15.5e} {:15.5e} {:11.1e}'
        #          .format(ntiter, gap, pobj, dobj, s))

        if (gap / dobj) < reltol:
            status = 'Solved'
            history = np.vstack([np.asarray(pobjs) - np.asarray(dobjs),
                                 pobjs, dobjs, sts, pflgs]).transpose()
            #if not quiet:
            #    print('Absolute tolerance reached.')

            break

        # Update t
        if s >= 0.5:
            t = max(min(2 * n * MU / gap, MU * t), t)

        # Calculate Newton step
        q1, q2 = 1 / (u + x), 1 / (u - x)
        d1, d2 = (q1 ** 2 + q2 ** 2) / t, (q1 ** 2 - q2 ** 2) / t

        # calculate the gradient
        gradphi = np.hstack([At.dot(2 * z) - (q1 - q2) / t,
                             lmbda * np.ones(n) - (q1 + q2) / t])

        # calculate vectors to be used in the preconditioner
        prb = diagxtx + d1
        prs = prb.dot(d1) - (d2 ** 2)

        # set pcg tolerange (relative)
        normg = norm(gradphi)
        pcgtol = min(1e-1, eta * gap / min(1, normg))

        p1, p2, p3 = d1 / prs, d2 / prs, prb / prs
        dxu_old = dxu

        [dxu, info] = cg(AXfunc(A, At, d1, d2, p1, p2, p3),
                         -gradphi, x0=dxu, tol=pcgtol, maxiter=pcgmaxi,
                         M=MXfunc(A, At, d1, d2, p1, p2, p3))

        # This is to increase the tolerance of the underlying PCG if
        # it converges to the same solution without offering an increase
        # in the solution of the actual problem
        if info == 0 and np.all(dxu_old == dxu):
            pcgtol *= 0.1
            pflg = 0
        elif info < 0:
            pflg = -1
            raise TypeError('Incorrectly formulated problem.'
                            'Could not run PCG on it.')
        elif info > 0:
            pflg = 1
            if not quiet:
                print('Could not converge PCG after {} iterations.'
                      ''.format(info))
        else:
            pflg = 0

        dx, du = dxu[:n], dxu[n:]

        # Backtracking line search
        phi = z.dot(z) + lmbda * np.sum(u) - np.sum(np.log(-f)) / t
        s = 1.0
        gdx = gradphi.dot(dxu)
        for lsiter in range(MAX_LS_ITER):
            newx, newu = x + s * dx, u + s * du
            newf = np.hstack([newx - newu, -newx - newu])
            if np.max(newf) < 0:
                newz = A.dot(newx) - y
                newphi = newz.dot(newz) +                     lmbda * np.sum(newu) - np.sum(np.log(-newf)) / t
                if newphi - phi <= ALPHA * s * gdx:
                    break
            s = BETA * s
        else:
            if not quiet:
                print('MAX_LS_ITER exceeded in BLS')
            status = 'Failed'
            history = np.vstack([np.asarray(pobjs) - np.asarray(dobjs),
                                 pobjs, dobjs, sts, pflgs]).transpose()
            break

        x, u, f = newx, newu, newf
    else:
        if not quiet:
            print('MAX_NT_ITER exceeded.')
        status = 'Failed'
        history = np.vstack([np.asarray(pobjs) - np.asarray(dobjs),
                             pobjs, dobjs, sts, pflgs]).transpose()

    # Reshape x if the original array was a 2D
    if x0 is not None:
        x = x.reshape(*x0.shape)

    return (x, status, history)


def AXfunc(A, At, d1, d2, p1, p2, p3):
    """
    Returns a linear operator which computes A * x for PCG.

        y = hessphi * [x1; x2],

        where hessphi = [ A'*A*2+D1, D2;
                          D2,        D1]
    """

    def matvec(vec):
        n = vec.shape[0] // 2
        x1 = vec[:n]
        x2 = vec[n:]

        return np.hstack([At.dot(A.dot(x1) * 2) + d1 * x1 + d2 * x2,
                          d2 * x1 + d1 * x2])

    N = 2 * d1.shape[0]
    return LinearOperator((N, N), matvec=matvec)


def MXfunc(A, At, d1, d2, p1, p2, p3):
    """
    Compute P^{-1}X (PCG)

    y = P^{-1}*x
    """

    def matvec(vec):
        n = vec.shape[0] // 2
        x1 = vec[:n]
        x2 = vec[n:]

        return np.hstack([p1 * x1 - p2 * x2,
                          -p2 * x1 + p3 * x2])

    N = 2 * p1.shape[0]
    return LinearOperator((N, N), matvec=matvec)


def RSC(D, D_labels, y):
    classnum = 7
    nIter = 5
    mean_x = np.mean(D, 1).reshape((-1, 1))
    ll = np.shape(D)[1]
    lmbda = 0.4
    #sigma = 0.5
    beta = 0.1
    iter = 2
    residual = pow((y-mean_x), 2)
    temp = -beta*(residual-iter)
    temp1 = pow(math.e, temp)
    w = temp1/(temp1 + 1)
    w_y_o = w * y
    norm_w_y_o = np.linalg.norm(w_y_o, ord=2)
    for i in range(nIter):
        print('.', end="")
        ww = w/max(w)
        index_w = np.where(ww >= 1e-3)[0]
        w_index = np.reshape(w[index_w], (-1, 1))
        WW_index = np.tile(w_index, ll)
        W_D = WW_index*D[index_w, :]
        W_y = w[index_w]*y[index_w]
        #ratio = np.linalg.norm(W_y, ord=2)/norm_w_y_o
        rel_tol = 1
        [temp_s, status, hist] = l1ls(W_D, W_y, lmbda, tar_gap=rel_tol)
        temp_s = temp_s.reshape(-1, 1)
        residual = pow((y-np.dot(D, temp_s)), 2)
        temp2 = -beta*(residual-iter)
        temp3 = pow(math.e, temp2)
        w = temp3/(1 + temp3)
    gap1 = np.zeros((7))
    for cla in range(classnum):
        tt = np.where(D_labels == cla)
        tt = np.array(tt)[0].reshape(-1)
        s = temp_s[tt]
        D_t = D[:, tt]
        z1 = w * (y - np.dot(D_t, s))
        gap1[cla] = np.dot(z1.T, z1)
    gap1 = gap1.tolist()
    minerr = min(gap1)
    index = gap1.index(minerr)
    id = index
    return id

#????????????
# D = np.load('C:/matlab/python_cloud/cloud_res50/D.npy')
# D_labels = np.load('C:/matlab/python_cloud/cloud_res50/train_label.npy')
# label = np.load('C:/matlab/python_cloud/cloud_res50/test_label.npy')
# D_labels = D_labels.reshape((-1, 1))
# label = label.reshape((-1, 1))
# Y = np.load('C:/matlab/python_cloud/cloud_res50/Y.npy')
# fi = 0
# for j in range(3199):
#     y = Y[:, j].reshape((-1, 1))
#     id = RSC(D, D_labels, y)
#     print('???'+str(j+1)+'?????????????????????'+str(id))
#     print('???'+str(j+1)+'??????????????????'+str(label[j, 0]))
#     if(id == label[j, 0]):
#         print('????????????')
#     else:
#         print('????????????')
#         fi = fi+1
#     print('?????????????????????'+str(fi))





