"""Helpers for the new pipeline's analysis modules."""
import numpy as np
import pandas as pd
import statsmodels.api as sm

import config


def ols(y, X, cov_type="HC3", groups=None):
    X = sm.add_constant(X, has_constant="add")
    if cov_type == "cluster":
        return sm.OLS(y, X).fit(cov_type="cluster", cov_kwds={"groups": groups})
    return sm.OLS(y, X).fit(cov_type=cov_type)


def tidy(res, model, **extra):
    out = pd.DataFrame({"model": model, "term": res.params.index, "coef": res.params.values,
                        "se": res.bse.values, "t": res.tvalues.values, "p": res.pvalues.values})
    out["n"] = int(res.nobs)
    out["r2"] = res.rsquared
    out["adj_r2"] = res.rsquared_adj
    for k, v in extra.items():
        out[k] = v
    return out


def pairs_bootstrap(x, y, reps, seed):
    rng = np.random.RandomState(seed)
    x, y = np.asarray(x, float), np.asarray(y, float)
    n = len(y)
    b = np.empty(reps)
    for i in range(reps):
        idx = rng.randint(0, n, n)
        b[i] = sm.OLS(y[idx], sm.add_constant(x[idx])).fit().params[1]
    return b


def save(df, name):
    path = config.TABLES / name
    df.to_csv(path, index=False)
    return path
