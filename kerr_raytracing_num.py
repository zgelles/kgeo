# Hacky numeric raytracing from formalism in Gralla+Lupsasa 2019a,b
# 19a: https://arxiv.org/pdf/1910.12881.pdf
# 19b: https://arxiv.org/pdf/1910.12873.pdf

import numpy as np
import scipy.special as sp
import mpmath
import matplotlib.pyplot as plt
from tqdm import tqdm
from scipy.integrate import solve_ivp

from kerr_raytracing_utils import *
from gsl_ellip_binding import ellip_pi_gsl

ROUT = 1000 #4.e10 # sgra distance in M
NGEO = 100
NPIX = 500
MINSPIN = 1.e-6 # minimum spin for full formulas to work before taking limits.
EP = 1.e-12

#a = 0.94;th_o=20*np.pi/180.; r_o=ROUT; alpha = np.linspace(-6,6,NPIX);beta=-0.001*np.ones(NPIX);ngeo=NGEO
def raytrace_num(a=0.94, th_o=20*np.pi/180., r_o=ROUT,
                 alpha=np.linspace(-6,6,NPIX), beta=-0.001*np.ones(NPIX), ngeo=NGEO):
    # checks
    if not (isinstance(a,float) and (0<=a<1)):
        raise Exception("a should be float in range [0,1)")
    if not (isinstance(th_o,float) and (0<th_o<=np.pi/2.)):
        raise Exception("th_o should be float in range (0,pi/2)")
    if not isinstance(alpha, np.ndarray): lam = np.array([lam]).flatten()
    if not isinstance(beta, np.ndarray): eta = np.array([eta]).flatten()
    if len(alpha) != len(beta):
        raise Exception("alpha, beta are different lengths!")

    # horizon radii
    rplus  = 1 + np.sqrt(1-a**2)
    rminus = 1 - np.sqrt(1-a**2)

    # conserved quantities
    lam = -alpha*np.sin(th_o)
    eta = (alpha**2 - a**2)*np.cos(th_o)**2 + beta**2
    if(np.any(eta==0)):
        raise Exception("there are points where eta is exactly 0!") # TODO

    # angular turning points
    (u_plus, u_minus, th_plus, th_minus, thclass) = angular_turning(a, th_o, lam, eta)

    # radial roots and radial motion case
    (r1, r2, r3, r4, rclass) = radial_roots(a, lam, eta)

    # total Mino time to infinity
    tau_tot = mino_total(a, r_o, eta, r1, r2, r3, r4)

    # find the steps in tau
    # go to taumax in the same number of steps on each ray -- step dtau depends on the ray
    maxtaufrac = (1. - 1.e-12) # NOTE: if we go exactly to tau_tot, t and phi diverge on horizon
    taumax = maxtaufrac*tau_tot / (ngeo - 1)

    # find the number of poloidal orbits as a function of time (GL 19b Eq 35)
    # Only applies for normal geodesics eta>0
    K = sp.ellipkinc(np.pi/2., u_plus/u_minus) # gives NaN for eta<0
    n_all = (a*np.sqrt(-u_minus.astype(complex))*tausteps)/(4*K)
    n_all = np.real(n_all.astype(complex))
    n_tot = n_all[-1]

    # fractional number of equatorial crossings
    # Only applies for normal geodesics eta>0
    F_o = sp.ellipkinc(np.arcsin(np.cos(th_o)/np.sqrt(u_plus)), u_plus/u_minus) # gives NaN for eta<0
    # TODO is my_sign right at beta=0??
    Nmax_eq = ((tau_tot*np.sqrt(-u_minus.astype(complex) * a**2) + my_sign(beta)*F_o) / (2*K))  + 1
    Nmax_eq[beta>=0] -= 1
    Nmax_eq = np.floor(np.real(Nmax_eq.astype(complex)))

    tau_num_all = []
    x_num_all = []
    for i in tqdm(range(NPIX)):
        tau_num, x_num = integrate_geo_single(a,th_o, r_o,alpha[i],beta[i],taumax[i],
                                              ngeo=NGEO,verbose=False)
        tau_num_all.append(tau_num)
        x_num_all.append(x_num)
    tau_num_all = np.array(tau_num)
    x_num_all = np.array(x_num)

    #return (t_s, r_s, th_s, phi_s,sig_s)

# directly integrate
def dxdtau(tau,x,a,lam,eta,sr,sth):
    t = x[0]
    r = x[1]
    th = x[2]
    ph = x[3]
    sig = x[4]

    Delta = r**2 - 2*r + a**2
    Sigma = r**2 + (a**2) * (np.cos(th)**2)

    R = (r**2 + a**2 -a*lam)**2 - Delta*(eta + (lam-a)**2)
    TH = eta + (a*np.cos(th))**2 - (lam/np.tan(th))**2

    if R<0: R=0.
    if TH<0: TH=0.

    dt = (r**2 + a**2)*(r**2 + a**2 - a*lam)/Delta + a*(lam-a*np.sin(th)**2)
    dr = sr*np.sqrt(R)
    dth = sth*np.sqrt(TH)
    dph = a*(r**2 + a**2 - a*lam)/Delta + lam/(np.sin(th)**2) - a
    dsig = Sigma

    return np.array([dt,dr,dth,dph,dsig])

def jac(tau,x,a,lam,eta,sr,sth):
    t = x[0]
    r = x[1]
    th = x[2]
    ph = x[3]
    sig = x[4]

    Delta = r**2 - 2*r + a**2
    Sigma = r**2 + a**2 * np.cos(th)**2

    R = (r**2 + a**2 -a*lam)**2 - Delta*(eta + (lam-a)**2)
    TH = eta + (a*np.cos(th))**2 - (lam/np.tan(th))**2
    if R<0: R=0.
    if TH<0: TH=0.

    jacout = np.empty((5,5))
    jacout[0,0] = 0.
    jacout[0,1] = (-2*a*lam+4*a**2*r+4*r**3)/Delta - (2*r-2)*(a**4-2*a*lam*r+2*a**2*r**2+r**4)/(Delta**2)
    jacout[0,2] = -2*a**2*np.cos(th)*np.sin(th)
    jacout[0,3] = 0.
    jacout[0,4] = 0.

    jacout[1,0] = 0.
    jacout[1,1] = sr*(-(2*r-2)*(eta+(lam-a)**2) + 4*r*(a**2-a*lam+r**2))/(2*np.sqrt(R))
    jacout[1,2] = 0.
    jacout[1,3] = 0.
    jacout[1,4] = 0.

    jacout[2,0] = 0.
    jacout[2,1] = 0.
    jacout[2,2] = sth*((2*lam**2)/(np.tan(th)*np.sin(th)**2) - 2*a**2*np.cos(th)*np.sin(th))/(2*np.sqrt(TH))
    jacout[2,3] = 0.
    jacout[2,4] = 0.

    jacout[3,0] = 0.
    jacout[3,1] = 2*a*(a**2 + a*lam*(r-1)-r**2)/(Delta**2)
    jacout[3,2] = -2*lam/(np.tan(th)*np.sin(th)**2)
    jacout[3,3] = 0.
    jacout[3,4] = 0.

    jacout[4,0] = 0.
    jacout[4,1] = 2*r
    jacout[4,2] = -2*(a**2)*np.cos(th)*np.sin(th)
    jacout[4,3] = 0.
    jacout[4,4] = 0.

    return jacout

def eventR(t, x, a, lam, eta, sr, sth):
    t = x[0]
    r = x[1]
    th = x[2]
    ph = x[3]

    Delta = r**2 - 2*r + a**2
    R = (r**2 + a**2 -a*lam)**2 - Delta*(eta + (lam-a)**2)

    return R
eventR.terminal = True

def eventTH(t, x, a, lam, eta, sr, sth):
    t = x[0]
    r = x[1]
    th = x[2]
    ph = x[3]

    TH = eta + (a*np.cos(th))**2 - (lam/np.tan(th))**2

    if a<MINSPIN and eta<EP: # this is equatorial motion, TODO ok hack?
        TH=1
    return TH
eventTH.terminal = True

# TODO this method isn't terribly precise, because of kludge in swapping signs
def integrate_geo_single(a,th_o, r_o,aa,bb,taumax,ngeo=NGEO,verbose=False):
    #ll = lam[i]
    #ee = eta[i]
    #tmax = -taumax[i]
    #bb = beta[i]
    sr = 1
    sth = int(np.sign(bb))
    if sth==0: sth=1 # TODO right?

    if np.abs(bb)<1.e-6 and th_o!=np.pi/2.: #TODO ok? numeric integration does not work exactly on beta=0.
        bb = sth*1.e-6

    ll = -aa*np.sin(th_o)
    ee = (aa**2 - a**2)*np.cos(th_o)**2 + bb**2

    tmax = -taumax # define tau positive in input, negative back into spacetime
    ts = []
    xs = []
    x0 = np.array([0,r_o,th_o,0,0])
    t0 = 0.
    x = x0
    t = t0
    max_step = np.abs(tmax/ngeo)
    min_step = np.abs(tmax/(ngeo*100))


    nswitch = 0
    while True:
        sol = solve_ivp(dxdtau, (t,tmax), x, method='DOP853', max_step=max_step,
                        #jac=jac,
                        rtol=1.e-8,atol=1.e-8,
                        args=(a,ll,ee,sr,sth), events=(eventTH,eventR))

        if verbose:
            print('status:', sol.status)

        ts.append(sol.t)
        xs.append(sol.y)

        if nswitch > 10:
            break
        if sol.status == 1:
            t = sol.t[-1]
            x = (sol.y[:,-1].copy())
            tm1 = sol.t[-2]
            xm1 = (sol.y[:,-2].copy())

            if sol.t_events[1].size != 0:
                sr *= -1
                rturn = sol.y_events[1][0][1]
                if verbose:
                    print('changing r sign')
            if sol.t_events[0].size != 0:
                sth *= -1
                thturn = sol.y_events[0][0][2]
                if verbose:
                    print('changing th sign',sth)

            fac = 1.e-8
            dt = fac*(t-tm1)
            dx = fac*(x-xm1)
            t = t-dt
            x = x-dx

            nswitch += 1
        else:
            break


    ts = np.concatenate(ts)
    xs = np.concatenate(xs, axis=1)

    # transform phi to range (-pi/2,pi/2)
    #xs[3] = np.mod(xs[3] - np.pi, 2*np.pi) - np.pi  # put in range (-pi,pi)

    return (ts, xs)
