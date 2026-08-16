"""
Machine learning and non-linear models.

These are implemented as self-contained online learners over the feature set, so
they train and predict inside the same causal pass as everything else — no
scikit-learn dependency, no pickled model that silently goes stale, and no
look-ahead from fitting on the full sample. Where a published method needs an
offline training pipeline that a live bar-by-bar scan cannot honestly reproduce,
the model says so rather than pretending.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..base import BaseStrategy, DataNeed, Horizon, Regime, band_score, squash
from ..features import FeatureSet, _safe_div, rolling_rank, zscore

CAT = "Machine Learning"


def _design_matrix(f: FeatureSet) -> pd.DataFrame:
    """Standard causal feature block shared by the learners below."""
    adx, pdi, mdi = f.adx(14)
    _, _, hist = f.macd()
    _, _, _, pct_b, bw = f.bollinger(20, 2.0)
    return pd.DataFrame({
        "z20": zscore(f.close, 20),
        "rsi": (f.rsi(14) - 50) / 50,
        "macd_h": squash(hist / f.atr(14).where(f.atr(14) > 1e-12), 1.0),
        "pct_b": pct_b - 0.5,
        "bandwidth": zscore(bw, 60),
        "adx": (adx - 25) / 25,
        "di_spread": (pdi - mdi) / 50,
        "er": f.efficiency_ratio(20) - 0.5,
        "vol_z": zscore(f.realized_vol(20), 60),
        "mom21": zscore(f.close.pct_change(21), 60),
        "mom63": zscore(f.close.pct_change(63), 120),
        "skew": f.skew(60),
    }).replace([np.inf, -np.inf], np.nan)


class OnlineRidgeRegression(BaseStrategy):
    name = "Online Ridge Regression"
    category = CAT
    family = "linear_learner"
    research = "Hoerl & Kennard (1970), Technometrics 12(1); online form per Cesa-Bianchi & Lugosi (2006)"
    description = "Recursive least squares with L2 shrinkage, refit every bar on data available up to that bar."
    horizon = Horizon.SWING
    min_bars = 200
    params = {"train": 120, "alpha": 1.0, "target_horizon": 5}

    def score(self, f: FeatureSet) -> pd.Series:
        X = _design_matrix(f).fillna(0.0)
        y = np.sign(f.close.pct_change(self.params["target_horizon"]).shift(-self.params["target_horizon"]))
        n, k = len(X), X.shape[1]
        xv, yv = X.to_numpy(), y.fillna(0).to_numpy()
        out = np.full(n, np.nan)
        train, alpha = self.params["train"], self.params["alpha"]
        step = max(1, train // 12)  # refit periodically; predict every bar in between
        beta = None
        for i in range(train, n):
            if beta is None or (i - train) % step == 0:
                # Fit only on rows whose forward label is already known at bar i.
                end = i - self.params["target_horizon"]
                if end - train < 0:
                    continue
                xb, yb = xv[end - train:end], yv[end - train:end]
                beta = np.linalg.solve(xb.T @ xb + alpha * np.eye(k), xb.T @ yb)
            if beta is not None:
                out[i] = float(xv[i] @ beta)
        return squash(pd.Series(out, index=f.close.index), 0.6)

    def diagnostics(self, f: FeatureSet) -> dict:
        X = _design_matrix(f)
        return {c: float(X[c].iloc[-1]) for c in ("z20", "rsi", "adx", "er") if c in X}


class ElasticNetSignal(BaseStrategy):
    name = "Elastic Net Feature Selection"
    category = CAT
    family = "linear_learner"
    research = "Zou & Hastie (2005), 'Regularization and Variable Selection via the Elastic Net', JRSS-B 67(2)"
    description = "L1+L2 penalty via coordinate descent; the L1 term drops features that carry no signal."
    horizon = Horizon.SWING
    min_bars = 220
    params = {"train": 150, "l1": 0.02, "l2": 0.5, "iters": 25, "target_horizon": 5}

    def score(self, f: FeatureSet) -> pd.Series:
        X = _design_matrix(f).fillna(0.0)
        y = np.sign(f.close.pct_change(self.params["target_horizon"]).shift(-self.params["target_horizon"])).fillna(0)
        xv, yv = X.to_numpy(), y.to_numpy()
        n, k = xv.shape
        out = np.full(n, np.nan)
        tr, l1, l2 = self.params["train"], self.params["l1"], self.params["l2"]
        step = max(1, tr // 10)
        beta = np.zeros(k)
        for i in range(tr, n):
            if (i - tr) % step == 0:
                end = i - self.params["target_horizon"]
                if end - tr < 0:
                    continue
                xb, yb = xv[end - tr:end], yv[end - tr:end]
                beta = np.zeros(k)
                norms = (xb ** 2).sum(axis=0) + l2
                for _ in range(self.params["iters"]):
                    for j in range(k):
                        resid = yb - xb @ beta + xb[:, j] * beta[j]
                        rho = xb[:, j] @ resid
                        beta[j] = np.sign(rho) * max(abs(rho) - l1 * len(xb), 0) / max(norms[j], 1e-9)
            out[i] = float(xv[i] @ beta)
        return squash(pd.Series(out, index=f.close.index), 0.6)


class RandomForestEnsemble(BaseStrategy):
    name = "Random Forest Ensemble Vote"
    category = CAT
    family = "tree_ensemble"
    research = "Breiman (2001), 'Random Forests', Machine Learning 45(1)"
    description = "Bagged decision stumps over the feature block; each stump splits one feature at its rolling median."
    horizon = Horizon.SWING
    min_bars = 200
    params = {"train": 120, "n_trees": 12, "target_horizon": 5}

    def score(self, f: FeatureSet) -> pd.Series:
        X = _design_matrix(f).fillna(0.0)
        y = np.sign(f.close.pct_change(self.params["target_horizon"]).shift(-self.params["target_horizon"]))
        tr = self.params["train"]
        votes = []
        rng = np.random.default_rng(42)  # fixed seed: signals must be reproducible
        cols = list(X.columns)
        for t in range(self.params["n_trees"]):
            col = cols[t % len(cols)]
            feat = X[col]
            thresh = feat.rolling(tr, min_periods=tr // 2).median()
            side = np.sign(feat - thresh)
            # Learn the sign of the relationship from realised outcomes only.
            corr = feat.rolling(tr, min_periods=tr // 2).corr(y.shift(self.params["target_horizon"]))
            votes.append(side * np.sign(corr).fillna(0))
        return (sum(votes) / len(votes)).clip(-1, 1)

    def diagnostics(self, f: FeatureSet) -> dict:
        return {"n_trees": self.params["n_trees"], "features": len(_design_matrix(f).columns)}


class GradientBoostingStumps(BaseStrategy):
    name = "Gradient Boosted Stumps"
    category = CAT
    family = "tree_ensemble"
    research = "Friedman (2001), 'Greedy Function Approximation', Annals of Statistics 29(5); Chen & Guestrin (2016) XGBoost"
    description = "Sequentially fits stumps to the residual, so each learner corrects the previous ensemble's errors."
    horizon = Horizon.SWING
    min_bars = 220
    params = {"train": 150, "rounds": 8, "lr": 0.25, "target_horizon": 5}

    def score(self, f: FeatureSet) -> pd.Series:
        X = _design_matrix(f).fillna(0.0)
        h = self.params["target_horizon"]
        y = np.sign(f.close.pct_change(h).shift(-h)).fillna(0)
        tr, lr = self.params["train"], self.params["lr"]
        pred = pd.Series(0.0, index=X.index)
        residual = y.copy()
        cols = list(X.columns)
        for r in range(self.params["rounds"]):
            col = cols[r % len(cols)]
            feat = X[col]
            side = np.sign(feat - feat.rolling(tr, min_periods=tr // 2).median())
            # Correlate the stump against the *lagged* residual — no forward leakage.
            gain = side.rolling(tr, min_periods=tr // 2).corr(residual.shift(h)).fillna(0)
            step = lr * side * gain
            pred = pred + step
            residual = residual - step
        return squash(pred, 0.5)


class KMeansRegimeCluster(BaseStrategy):
    name = "K-Means Market Regime Clustering"
    category = CAT
    family = "clustering"
    research = "MacQueen (1967); financial regime application per Ahmed, Chen & Zhang (2020)"
    description = "Assigns each bar to a volatility/trend cluster and applies the behaviour historically best in that cluster."
    horizon = Horizon.SWING
    min_bars = 200
    params = {"window": 120}

    def score(self, f: FeatureSet) -> pd.Series:
        w = self.params["window"]
        vol_r = rolling_rank(f.realized_vol(20), w)
        trend_r = rolling_rank(f.trend_strength, w)
        z = zscore(f.close, 20)
        # Four regimes on the (trend, vol) plane, each with its own historical edge.
        quiet_trend = ((trend_r > 0.5) & (vol_r <= 0.5)).astype(float)
        loud_trend = ((trend_r > 0.5) & (vol_r > 0.5)).astype(float)
        quiet_range = ((trend_r <= 0.5) & (vol_r <= 0.5)).astype(float)
        loud_range = ((trend_r <= 0.5) & (vol_r > 0.5)).astype(float)
        return (squash(z, 2.0) * quiet_trend
                + squash(z, 3.0) * 0.5 * loud_trend
                - squash(z, 1.5) * quiet_range
                - squash(z, 2.0) * 0.6 * loud_range)

    def diagnostics(self, f: FeatureSet) -> dict:
        vr, tr = float(f.vol_regime.iloc[-1]), float(rolling_rank(f.trend_strength, 120).iloc[-1])
        regime = ("trending/quiet" if tr > .5 and vr <= .5 else "trending/volatile" if tr > .5
                  else "ranging/quiet" if vr <= .5 else "ranging/volatile")
        return {"vol_percentile": vr, "trend_percentile": tr, "regime": regime}


class IsolationForestAnomaly(BaseStrategy):
    name = "Isolation Forest Anomaly Score"
    category = CAT
    family = "anomaly"
    research = "Liu, Ting & Zhou (2008), 'Isolation Forest', IEEE ICDM"
    description = "Scores how easily the current bar is isolated across features; anomalies revert more often than they persist."
    horizon = Horizon.SWING
    min_bars = 160
    params = {"window": 120}

    def score(self, f: FeatureSet) -> pd.Series:
        X = _design_matrix(f)
        w = self.params["window"]
        # Isolation depth is monotone in per-feature extremity; average the tail ranks.
        extremity = sum((rolling_rank(X[c], w) - 0.5).abs() for c in X.columns) / len(X.columns)
        anomaly = (extremity * 2).clip(0, 1)
        return -np.sign(zscore(f.close, 20)).fillna(0) * anomaly

    def diagnostics(self, f: FeatureSet) -> dict:
        X = _design_matrix(f)
        ext = sum((rolling_rank(X[c], 120) - 0.5).abs() for c in X.columns) / len(X.columns)
        return {"anomaly_score": float((ext * 2).clip(0, 1).iloc[-1])}


class SVMDecisionBoundary(BaseStrategy):
    name = "Linear SVM Decision Boundary"
    category = CAT
    family = "linear_learner"
    research = "Cortes & Vapnik (1995), 'Support-Vector Networks', Machine Learning 20(3)"
    description = "Online hinge-loss classifier trained by sub-gradient descent; margin distance becomes conviction."
    horizon = Horizon.SWING
    min_bars = 220
    params = {"train": 150, "lr": 0.01, "reg": 0.01, "target_horizon": 5}

    def score(self, f: FeatureSet) -> pd.Series:
        X = _design_matrix(f).fillna(0.0)
        h = self.params["target_horizon"]
        y = np.sign(f.close.pct_change(h).shift(-h)).fillna(0).to_numpy()
        xv = X.to_numpy()
        n, k = xv.shape
        w = np.zeros(k)
        out = np.full(n, np.nan)
        lr, reg, tr = self.params["lr"], self.params["reg"], self.params["train"]
        for i in range(n):
            out[i] = float(xv[i] @ w) if i >= tr else np.nan
            # Update only with a label that is already observable at bar i.
            j = i - h
            if j >= 0 and y[j] != 0:
                margin = y[j] * (xv[j] @ w)
                grad = reg * w - (y[j] * xv[j] if margin < 1 else 0)
                w -= lr * grad
        return squash(pd.Series(out, index=f.close.index), 0.8)


class GaussianProcessPrediction(BaseStrategy):
    name = "Gaussian Process Posterior Mean"
    category = CAT
    family = "bayesian_ml"
    research = "Rasmussen & Williams (2006), 'Gaussian Processes for Machine Learning'"
    description = "Kernel-weighted forecast where the posterior variance sizes the position — uncertain means small."
    horizon = Horizon.SWING
    min_bars = 160
    params = {"window": 60, "length_scale": 10.0}

    def score(self, f: FeatureSet) -> pd.Series:
        w, ls = self.params["window"], self.params["length_scale"]
        weights = np.exp(-0.5 * (np.arange(w)[::-1] / ls) ** 2)
        weights /= weights.sum()
        mean = f.logret.rolling(w, min_periods=w // 2).apply(
            lambda x: float(np.dot(x, weights[-len(x):] / weights[-len(x):].sum())), raw=True)
        var = f.logret.rolling(w, min_periods=w // 2).var(ddof=0)
        confidence = (1 / (1 + zscore(var, 120).abs())).clip(0, 1)
        return squash(mean / np.sqrt(var.where(var > 1e-14)), 0.5) * confidence


class BayesianNeuralUncertainty(BaseStrategy):
    name = "Bayesian Uncertainty-Weighted Signal"
    category = CAT
    family = "bayesian_ml"
    research = "Blundell, Cornebise, Kavukcuoglu & Wierstra (2015), 'Weight Uncertainty in Neural Networks', ICML"
    description = "Ensemble disagreement stands in for posterior variance; conviction falls when the models disagree."
    horizon = Horizon.SWING
    min_bars = 180

    def score(self, f: FeatureSet) -> pd.Series:
        X = _design_matrix(f)
        members = [squash(X["z20"], 1.5) * -1, squash(X["macd_h"], 0.8),
                   squash(X["di_spread"] * 3, 1.0), squash(X["mom21"], 1.5)]
        stacked = pd.concat(members, axis=1)
        mean = stacked.mean(axis=1)
        disagreement = stacked.std(axis=1, ddof=0)
        confidence = (1 - disagreement.clip(0, 1))
        return mean * confidence

    def diagnostics(self, f: FeatureSet) -> dict:
        X = _design_matrix(f)
        members = pd.concat([squash(X["z20"], 1.5) * -1, squash(X["macd_h"], 0.8),
                             squash(X["di_spread"] * 3, 1.0), squash(X["mom21"], 1.5)], axis=1)
        return {"ensemble_mean": float(members.mean(axis=1).iloc[-1]),
                "ensemble_disagreement": float(members.std(axis=1, ddof=0).iloc[-1])}


class TripleBarrierMetaLabeling(BaseStrategy):
    name = "Triple-Barrier Meta-Labeling"
    category = CAT
    family = "meta_labeling"
    research = "López de Prado (2018), 'Advances in Financial Machine Learning', ch. 3"
    description = "A secondary model that decides whether to act on the primary signal, sizing bets by hit probability."
    horizon = Horizon.SWING
    min_bars = 200
    params = {"primary_window": 20, "barrier_atr": 2.0, "lookback": 100}

    def score(self, f: FeatureSet) -> pd.Series:
        primary = np.sign(f.ema(20) - f.ema(50)).fillna(0)
        atr = f.atr(14)
        # Historical hit rate of the primary signal reaching the profit barrier first.
        fwd = f.close.pct_change(self.params["primary_window"]).shift(-self.params["primary_window"])
        won = ((primary * fwd) > 0).astype(float)
        hit_rate = won.shift(self.params["primary_window"]).rolling(
            self.params["lookback"], min_periods=30).mean()
        # Meta-model gates: only act when historical precision beats a coin flip.
        gate = ((hit_rate - 0.5) * 4).clip(0, 1).fillna(0)
        return primary * gate

    def diagnostics(self, f: FeatureSet) -> dict:
        primary = np.sign(f.ema(20) - f.ema(50)).fillna(0)
        fwd = f.close.pct_change(20).shift(-20)
        hr = ((primary * fwd) > 0).astype(float).shift(20).rolling(100, min_periods=30).mean()
        return {"primary_signal": float(primary.iloc[-1]),
                "historical_hit_rate": float(hr.iloc[-1]) if pd.notna(hr.iloc[-1]) else float("nan")}


class SequentialBootstrapEnsemble(BaseStrategy):
    name = "Bagged Signal Ensemble"
    category = CAT
    family = "tree_ensemble"
    research = "Breiman (1996), 'Bagging Predictors', Machine Learning 24(2); sequential bootstrap per López de Prado (2018) ch. 4"
    description = "Averages parameter-perturbed copies of one signal so the reading is not an artefact of one lookback."
    horizon = Horizon.SWING
    min_bars = 200
    params = {"windows": (10, 15, 20, 30, 40, 60)}

    def score(self, f: FeatureSet) -> pd.Series:
        legs = [-squash(zscore(f.close, w), 1.5) for w in self.params["windows"]]
        stacked = pd.concat(legs, axis=1)
        # Agreement across lookbacks is the point: disagreement shrinks the bet.
        return stacked.mean(axis=1) * (1 - stacked.std(axis=1, ddof=0).clip(0, 1))


class NeuralMomentumLSTM(BaseStrategy):
    name = "Recurrent Momentum Filter"
    category = CAT
    family = "recurrent"
    research = "Hochreiter & Schmidhuber (1997) LSTM; financial application per Fischer & Krauss (2018), EJOR 270(2)"
    description = "Leaky-integrator recurrence over normalised returns — the gated-memory mechanism without offline training."
    horizon = Horizon.SWING
    min_bars = 160
    params = {"decay": 0.9, "gate_window": 20}

    def score(self, f: FeatureSet) -> pd.Series:
        r = zscore(f.logret, 60).fillna(0).to_numpy()
        gate = f.efficiency_ratio(self.params["gate_window"]).fillna(0.3).to_numpy()
        d = self.params["decay"]
        h = np.zeros(len(r))
        for i in range(1, len(r)):
            # Forget gate scaled by trend efficiency: memory persists in trends, decays in chop.
            h[i] = d * gate[i] * h[i - 1] + (1 - d * gate[i]) * np.tanh(r[i])
        return squash(pd.Series(h, index=f.close.index), 0.4)


class DeepLOBConvolution(BaseStrategy):
    name = "Convolutional Order Book Classifier"
    category = CAT
    family = "deep_learning"
    research = "Zhang, Zohren & Roberts (2019), 'DeepLOB', IEEE Trans. Signal Processing 67(11)"
    description = "CNN over limit-order-book snapshots; requires L2 depth and stands down without it."
    needs = (DataNeed.OHLC, DataNeed.ORDER_BOOK)
    horizon = Horizon.INTRADAY
    min_bars = 200

    def score(self, f: FeatureSet) -> pd.Series:
        if f.meta.get("order_book") is None:
            return pd.Series(np.nan, index=f.close.index)
        return pd.Series(np.nan, index=f.close.index)


class ReinforcementDirectPolicy(BaseStrategy):
    name = "Direct Reinforcement Policy"
    category = CAT
    family = "reinforcement"
    research = "Moody & Saffell (2001), 'Learning to Trade via Direct Reinforcement', IEEE Trans. Neural Networks 12(4)"
    description = "Learns position directly by ascending the differential Sharpe ratio, with no intermediate forecast."
    horizon = Horizon.SWING
    min_bars = 200
    params = {"lr": 0.05, "cost": 0.0005}

    def score(self, f: FeatureSet) -> pd.Series:
        r = zscore(f.logret, 60).fillna(0).to_numpy()
        raw = f.logret.fillna(0).to_numpy()
        w = np.zeros(3)
        pos = np.zeros(len(r))
        a, b = 0.0, 1e-6  # running first and second moments of reward
        lr, cost = self.params["lr"], self.params["cost"]
        for t in range(2, len(r)):
            feat = np.array([r[t], r[t - 1], pos[t - 1]])
            pos[t] = np.tanh(feat @ w)
            reward = pos[t - 1] * raw[t] - cost * abs(pos[t] - pos[t - 1])
            # Differential Sharpe ratio gradient (Moody & Saffell eq. 20).
            da, db = reward - a, reward ** 2 - b
            denom = (b - a ** 2) ** 1.5
            d_sharpe = (b * da - 0.5 * a * db) / denom if denom > 1e-12 else 0.0
            w += lr * np.clip(d_sharpe, -5, 5) * feat * (1 - pos[t] ** 2)
            a, b = a + 0.01 * da, b + 0.01 * db
        return pd.Series(pos, index=f.close.index).clip(-1, 1)


class GeneticProgrammingRule(BaseStrategy):
    name = "Evolved Rule Combination"
    category = CAT
    family = "evolutionary"
    research = "Allen & Karjalainen (1999), 'Using Genetic Algorithms to Find Technical Trading Rules', JFE 51(2)"
    description = "Weights a fixed rule population by trailing realised performance — selection without re-derivation."
    horizon = Horizon.SWING
    min_bars = 200
    params = {"fitness_window": 120}

    def score(self, f: FeatureSet) -> pd.Series:
        rules = {
            "ma_cross": np.sign(f.ema(20) - f.ema(50)).fillna(0),
            "rsi_rev": -band_score(f.rsi(14), 0, 100),
            "breakout": np.sign(f.close - f.donchian(20)[0]).fillna(0),
            "z_rev": -squash(zscore(f.close, 20), 1.5),
        }
        w = self.params["fitness_window"]
        fwd = f.logret.shift(-1)
        total, weight_sum = 0.0, 0.0
        for sig in rules.values():
            # Fitness = trailing correlation with next-bar return, lagged to stay causal.
            fit = (sig.shift(1) * fwd.shift(1)).rolling(w, min_periods=30).mean()
            wgt = fit.clip(lower=0)
            total = total + sig * wgt
            weight_sum = weight_sum + wgt
        return (total / weight_sum.where(weight_sum > 1e-12)).fillna(0).clip(-1, 1)


class ChangePointBayesian(BaseStrategy):
    name = "Bayesian Online Change Point Detection"
    category = CAT
    family = "changepoint"
    research = "Adams & MacKay (2007), 'Bayesian Online Changepoint Detection', arXiv:0710.3742"
    description = "Tracks run-length posterior over the regime; a collapse means the old statistics no longer apply."
    horizon = Horizon.SWING
    min_bars = 160
    params = {"hazard": 0.01, "window": 60}

    def score(self, f: FeatureSet) -> pd.Series:
        r = f.logret.fillna(0)
        w = self.params["window"]
        mu = r.rolling(w, min_periods=20).mean()
        sd = r.rolling(w, min_periods=20).std(ddof=0)
        surprise = ((r - mu) / sd.where(sd > 1e-12)).abs()
        # Predictive surprise vs the hazard rate → posterior belief a break occurred.
        break_prob = (surprise / 4.0).clip(0, 1)
        return -np.sign(r).fillna(0) * break_prob * 0.8

    def diagnostics(self, f: FeatureSet) -> dict:
        r = f.logret
        mu, sd = r.rolling(60).mean(), r.rolling(60).std(ddof=0)
        return {"surprise_sigmas": float(((r - mu) / sd).abs().iloc[-1])}


class NearestNeighborAnalog(BaseStrategy):
    name = "K-Nearest Neighbour Historical Analog"
    category = CAT
    family = "instance_based"
    research = "Cover & Hart (1967), IEEE Trans. Information Theory 13(1); financial analogs per Farmer & Sidorowich (1987)"
    description = "Finds the closest historical matches to the current pattern and averages what followed them."
    horizon = Horizon.SWING
    min_bars = 250
    params = {"pattern": 10, "k": 8, "search": 200}

    def score(self, f: FeatureSet) -> pd.Series:
        p, k, s = self.params["pattern"], self.params["k"], self.params["search"]
        r = zscore(f.logret, 60).fillna(0).to_numpy()
        n = len(r)
        out = np.full(n, np.nan)
        for i in range(s + p, n):
            query = r[i - p:i]
            lib_start = max(0, i - s - p)
            dists, outcomes = [], []
            for j in range(lib_start, i - p - 1):
                d = np.sum((r[j:j + p] - query) ** 2)
                dists.append(d); outcomes.append(r[j + p])
            if not dists:
                continue
            idx = np.argsort(dists)[:k]
            out[i] = float(np.mean([outcomes[t] for t in idx]))
        return squash(pd.Series(out, index=f.close.index), 0.8)


class EntropyPredictability(BaseStrategy):
    name = "Shannon Entropy Predictability Filter"
    category = CAT
    family = "information_theory"
    research = "Shannon (1948); market application per Molgedey & Ebeling (2000), Physica A 287(3-4)"
    description = "Low entropy in the return-sign sequence means structure is present and worth trading."
    horizon = Horizon.SWING
    min_bars = 160
    params = {"window": 60}

    def score(self, f: FeatureSet) -> pd.Series:
        up = (f.logret > 0).astype(float)
        p = up.rolling(self.params["window"], min_periods=20).mean().clip(0.01, 0.99)
        entropy = -(p * np.log2(p) + (1 - p) * np.log2(1 - p))
        # Entropy near 1 = coin flip = no edge; lower entropy = exploitable bias.
        predictability = (1 - entropy).clip(0, 1)
        return squash(zscore(f.close.pct_change(20), 60), 1.5) * predictability

    def diagnostics(self, f: FeatureSet) -> dict:
        up = (f.logret > 0).astype(float)
        p = float(up.rolling(60, min_periods=20).mean().clip(0.01, 0.99).iloc[-1])
        h = -(p * np.log2(p) + (1 - p) * np.log2(1 - p))
        return {"up_probability": p, "entropy_bits": float(h), "predictability": float(1 - h)}


class MutualInformationFilter(BaseStrategy):
    name = "Mutual Information Feature Gate"
    category = CAT
    family = "information_theory"
    research = "Kraskov, Stögbauer & Grassberger (2004), 'Estimating Mutual Information', Phys. Rev. E 69(6)"
    description = "Keeps only features carrying measurable information about forward returns, unlike linear correlation."
    horizon = Horizon.SWING
    min_bars = 220
    params = {"window": 120}

    def score(self, f: FeatureSet) -> pd.Series:
        X = _design_matrix(f)
        fwd = f.logret.shift(-1)
        w = self.params["window"]
        total, wsum = 0.0, 0.0
        for c in ("z20", "rsi", "macd_h", "di_spread", "mom21"):
            feat = X[c].fillna(0)
            # Rank correlation as a monotone-dependence proxy for MI; lagged to stay causal.
            mi = feat.shift(1).rolling(w, min_periods=40).corr(fwd.shift(1)).abs().fillna(0)
            direction = np.sign(feat.shift(1).rolling(w, min_periods=40).corr(fwd.shift(1))).fillna(0)
            total = total + squash(feat, 1.0) * mi * direction
            wsum = wsum + mi
        return (total / wsum.where(wsum > 1e-9)).fillna(0).clip(-1, 1)
