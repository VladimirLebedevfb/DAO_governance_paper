"""Project configuration: paths, sample definitions, seeds, thresholds.

Everything that encodes a methodological choice lives here.
"""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# ---------------------------------------------------------------- paths
DATA_RAW = ROOT / "data" / "raw"              # cached API responses (Phase 2)
DATA_INTERIM = ROOT / "data" / "interim"
DATA_PROCESSED = ROOT / "data" / "processed"
REPORTS = ROOT / "reports"
TABLES = REPORTS / "tables"
FIGURES = REPORTS / "figures"

for _p in (DATA_RAW, DATA_INTERIM, DATA_PROCESSED, TABLES, FIGURES):
    _p.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------- APIs (Phase 2)
# Tally rebranded to Cactus on 2026-06-17; keys stay valid, the domain will move
# to cactushq.xyz. Override with TALLY_API_URL in .env when that happens.
TALLY_API_URL = os.getenv("TALLY_API_URL", "https://api.tally.xyz/query")
CRYPTOCOMPARE_BASE = "https://min-api.cryptocompare.com"
TALLY_MIN_INTERVAL = 1.1      # seconds between Tally requests (429 responses at shorter intervals)
CC_MIN_INTERVAL = 7.0         # key allows 10 calls per minute
CC_MONTHLY_BUDGET = 100       # key allows 100 calls per month; every call is logged

# Testnet chain ids (EIP-155): tokens there have no market price; excluded (rule U3b).
TESTNET_CHAINS = {"eip155:3", "eip155:4", "eip155:5", "eip155:42", "eip155:69", "eip155:97", "eip155:420",
                  "eip155:280", "eip155:300", "eip155:1442", "eip155:17000", "eip155:44787", "eip155:59140",
                  "eip155:59141", "eip155:80001", "eip155:80002", "eip155:84531", "eip155:84532",
                  "eip155:421611", "eip155:421613", "eip155:421614", "eip155:11155111", "eip155:11155420",
                  "eip155:168587773", "eip155:4202", "eip155:534351", "eip155:1946", "eip155:10200"}

# Delegate crawl depth (new pipeline): beyond the thesis top-100, to check coverage.
DELEGATE_MAX = 500
DELEGATE_COVERAGE_STOP = 0.999

# Tag of the fresh collection run (keys the raw cache files of paginated crawls).
COLLECTION_TAG = "2026-10"
COLLECTION_DATE = "2026-10-05"   # snapshot date of governance state and market caps

# ---------------------------------------------------------------- randomness
SEED = 42  # used by the thesis bootstrap (np.random.seed(42)); reused for placebo

# ---------------------------------------------------------------- sample period
SAMPLE_START = "2021-01-01"
SAMPLE_END_COLLECT = "2026-09-30"      # new pipeline: last full month before collection
BENCHMARK = "BTC"

# ---------------------------------------------------------------- event study
EVENT_WINDOW = (-5, 5)

# ---------------------------------------------------------------- new pipeline (fresh data)
# Kept equal to the thesis methods unless the author decides otherwise.
N_BOOT_NEW = 1000
N_PLACEBO_NEW = 1000           # thesis used 100; more reps only reduce simulation noise
N_WILD_BOOT = 999              # wild cluster bootstrap reps (H4, few clusters)
MIN_RETURN_MONTHS_NEW = 12     # the rule stated in the thesis text (it was not applied there)

# ---------------------------------------------------------------- figures
FIG_DPI = 300
FIG_FONT = ["Times New Roman", "DejaVu Serif"]
