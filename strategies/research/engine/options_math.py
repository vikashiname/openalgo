import numpy as np
from scipy.stats import norm
from scipy.optimize import brentq

def bs_price_and_greeks(S, K, T, r, sigma, option_type='CE'):
    """
    Computes Black-Scholes Price and Greeks.
    S: Underlying Price
    K: Strike Price
    T: Time to Expiration in Years (DTE / 365.0)
    r: Risk-free rate (annualized, e.g. 0.065 for India RBI repo / T-bill)
    sigma: Volatility (annualized, e.g. 0.15)
    """
    if T <= 0.0001:
        if option_type == 'CE':
            price = max(0.0, S - K)
            delta = 1.0 if S > K else 0.0
        else:
            price = max(0.0, K - S)
            delta = -1.0 if K > S else 0.0
        return {'price': price, 'delta': delta, 'gamma': 0.0, 'theta': 0.0, 'vega': 0.0}

    sigma = max(0.01, sigma)
    sqrt_T = np.sqrt(T)
    d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * sqrt_T)
    d2 = d1 - sigma * sqrt_T

    pdf_d1 = norm.pdf(d1)
    cdf_d1 = norm.cdf(d1)
    cdf_d2 = norm.cdf(d2)

    gamma = pdf_d1 / (S * sigma * sqrt_T)
    vega = S * sqrt_T * pdf_d1 / 100.0  # per 1% vol change

    if option_type == 'CE':
        price = S * cdf_d1 - K * np.exp(-r * T) * cdf_d2
        delta = cdf_d1
        theta = (- (S * pdf_d1 * sigma) / (2.0 * sqrt_T) - r * K * np.exp(-r * T) * cdf_d2) / 365.0
    else:
        cdf_neg_d1 = norm.cdf(-d1)
        cdf_neg_d2 = norm.cdf(-d2)
        price = K * np.exp(-r * T) * cdf_neg_d2 - S * cdf_neg_d1
        delta = cdf_d1 - 1.0
        theta = (- (S * pdf_d1 * sigma) / (2.0 * sqrt_T) + r * K * np.exp(-r * T) * cdf_neg_d2) / 365.0

    return {'price': price, 'delta': delta, 'gamma': gamma, 'theta': theta, 'vega': vega}

def implied_volatility(market_price, S, K, T, r=0.065, option_type='CE'):
    """Numerically solves for implied volatility."""
    if T <= 0.0001 or market_price <= 0.05:
        return 0.15
    intrinsic = max(0.0, (S - K) if option_type == 'CE' else (K - S))
    if market_price <= intrinsic:
        return 0.05

    def objective(sigma):
        return bs_price_and_greeks(S, K, T, r, sigma, option_type)['price'] - market_price

    try:
        iv = brentq(objective, 0.01, 3.0, xtol=1e-4)
        return iv
    except Exception:
        # Quick fallback approximation
        return 0.18

def calculate_option_delta(S, K, T, market_price, r=0.065, option_type='CE'):
    """Calculates delta given market price by inverting for IV."""
    iv = implied_volatility(market_price, S, K, T, r, option_type)
    return bs_price_and_greeks(S, K, T, r, iv, option_type)['delta']
