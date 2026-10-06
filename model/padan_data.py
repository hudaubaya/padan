"""Data sintetis identitas berkelompok dan perbandingan keputusan INT8 vs float.

Setiap identitas punya pusat acak c (vektor satuan, D dimensi). Sampelnya
normalize(c + sigma * u), u vektor satuan acak, sigma per sampel ~ U(SIGMA_LO,
SIGMA_HI) (variasi intra-kelas). Template = normalize(rata-rata ENROLL sampel).

Galeri: N identitas terdaftar. Probe: PROBES_PER_ID sampel baru dari tiap
identitas terdaftar (1 pasangan genuine + N-1 impostor per probe) dan
PROBES_PER_UNKNOWN sampel dari UNKNOWN identitas tak terdaftar (N impostor per
probe).

Float: terima jika cos(template, probe) >= tau.
INT8:  q = clip(round(x * SCALE), -127, 127), terima jika s = q_T . q_p >= tau_int,
       tau_int = round(tau * SCALE^2). SCALE tetap (global), dipilih agar
       |x_i| sampai CLIP_RMS * (1/sqrt(D)) tidak terpotong.
"""

import sys

import numpy as np

import padan as P

SEED = 2026
ENROLL = 4
SIGMA_LO, SIGMA_HI = 0.6, 2.0
PROBES_PER_ID = 200
UNKNOWN = 64
PROBES_PER_UNKNOWN = 50
CLIP_RMS = 4.0
SCALE = 127 / (CLIP_RMS / np.sqrt(P.D))
TAUS = (0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.50)


def normalize(x):
    return x / np.linalg.norm(x, axis=-1, keepdims=True)


def samples(rng, centers, k):
    """k sampel per pusat: (len(centers) * k, D), urut per identitas."""
    c = np.repeat(centers, k, axis=0)
    u = normalize(rng.standard_normal(c.shape))
    sigma = rng.uniform(SIGMA_LO, SIGMA_HI, (len(c), 1))
    return normalize(c + sigma * u)


def quantize(x):
    return np.clip(np.rint(x * SCALE), -127, 127).astype(np.int64)


def tau_int(tau):
    return int(round(tau * SCALE * SCALE))


def make_dataset(seed=SEED):
    rng = np.random.default_rng(seed)
    centers = normalize(rng.standard_normal((P.N, P.D)))
    unknown = normalize(rng.standard_normal((UNKNOWN, P.D)))
    enroll = samples(rng, centers, ENROLL).reshape(P.N, ENROLL, P.D)
    T = normalize(enroll.mean(axis=1))
    probes = np.concatenate([samples(rng, centers, PROBES_PER_ID),
                             samples(rng, unknown, PROBES_PER_UNKNOWN)])
    labels = np.concatenate([np.repeat(np.arange(P.N), PROBES_PER_ID),
                             np.full(UNKNOWN * PROBES_PER_UNKNOWN, -1)])
    Tq, pq = quantize(T), quantize(probes)
    return {
        "T": T, "probes": probes, "labels": labels, "Tq": Tq, "pq": pq,
        "cos": probes @ T.T,                    # (probe, template)
        "s": pq @ Tq.T,                         # skor integer, sama dengan P.scores per probe
        "genuine": labels[:, None] == np.arange(P.N)[None, :],
        "clipped": float(np.mean(np.abs(np.concatenate([T, probes]) * SCALE) > 127.5)),
    }


def evaluate(ds, taus=TAUS):
    g = ds["genuine"]
    rows = []
    for tau in taus:
        ti = tau_int(tau)
        acc_f = ds["cos"] >= tau
        acc_q = ds["s"] >= ti
        rows.append({
            "tau": tau, "tau_int": ti,
            "far_float": acc_f[~g].mean(), "frr_float": (~acc_f[g]).mean(),
            "far_int8": acc_q[~g].mean(), "frr_int8": (~acc_q[g]).mean(),
            "agree": (acc_f == acc_q).mean(), "disagree": int((acc_f != acc_q).sum()),
            # Pasangan yang berbeda keputusan: seberapa jauh cos dari ambang.
            "max_gap": float(np.abs(ds["cos"][acc_f != acc_q] - tau).max(initial=0.0)),
        })
    return rows


def summary(ds):
    g = ds["genuine"]
    err = ds["s"] / SCALE**2 - ds["cos"]
    return {
        "pairs": g.size, "genuine_pairs": int(g.sum()), "impostor_pairs": int((~g).sum()),
        "cos_gen_mean": ds["cos"][g].mean(), "cos_gen_p05": np.percentile(ds["cos"][g], 5),
        "cos_imp_mean": ds["cos"][~g].mean(), "cos_imp_p99": np.percentile(ds["cos"][~g], 99.9),
        "q_err_max": np.abs(err).max(), "q_err_rms": np.sqrt(np.mean(err**2)),
        "clipped": ds["clipped"], "s_absmax": int(np.abs(ds["s"]).max()),
    }


def self_test():
    ds = make_dataset()
    k = 7
    assert np.array_equal(ds["s"][k], P.scores(ds["Tq"], ds["pq"][k]))
    sm = summary(ds)
    assert sm["cos_gen_mean"] > sm["cos_imp_mean"] + 0.2
    assert sm["q_err_max"] < 0.05 and sm["s_absmax"] < 1 << 17
    assert ds["Tq"].min() >= -127 and ds["Tq"].max() <= 127
    rows = evaluate(ds)
    assert all(r["agree"] > 0.99 for r in rows)
    print("padan_data model: self-test OK")


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        self_test()
    else:
        ds = make_dataset()
        for k, v in summary(ds).items():
            print(f"{k:16s} {v}")
        for r in evaluate(ds):
            print(r)
