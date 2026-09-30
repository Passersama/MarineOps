import os

if os.environ.get("CARGO_TRACK_TRACE") == "1":
    print("runner: importing application", flush=True)
from cargo_track.main import main

if os.environ.get("CARGO_TRACK_TRACE") == "1":
    print("runner: entering application", flush=True)
raise SystemExit(main())
