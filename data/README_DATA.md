# Data Files

This directory contains two small Eclipse summary files that are committed to the
repository and used as the validation reference:

| File | Size | Purpose |
|------|------|---------|
| `FIELD_X_001.UNSMRY` | ~618 KB | Eclipse summary time series (rates, cumulatives, aquifer influx) |
| `FIELD_X_001.SMSPEC` | ~35 KB | Summary specification (mnemonic + well name index) |

---

## Large binary files (not committed)

The following files are required to run the full workflow but are too large to store
in this repository (~400 MB total).  They can be provided on request.

| File | Size | Purpose |
|------|------|---------|
| `FIELD_X_001.DATA` | ~160 MB | OPM Flow model definition (full inline DATA deck) |
| `FIELD_X_001.EGRID` | ~39 MB | 3D grid geometry |
| `FIELD_X_001.INIT` | ~27 MB | Static reservoir properties (PORO, PERMX, NTG, etc.) |
| `FIELD_X_001.UNRST` | ~167 MB | Dynamic Eclipse outputs (PRESSURE, SWAT, SGAS per timestep) |

### How to obtain

Send a request to the repository owner via LinkedIn (link in profile).  Files will be
shared via a private transfer link.

Alternatively, these files can be added to the repository later via
[Git LFS](https://git-lfs.com/) — the structure is already in place to support this.

---

## Place files here

Once obtained, place all binary files in this `data/` directory.  The `config.json`
at the repo root expects them at `data/FIELD_X_001.*`.
