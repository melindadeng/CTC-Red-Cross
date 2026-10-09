"""Flag repeated child identities for review; do not delete source records."""

from collections import defaultdict
from itertools import combinations
from pathlib import Path

import pandas as pd


base_dir = Path(__file__).resolve().parent
source_path = base_dir / "Interview_1_merged_cleaned.csv"
SAME_TIME_MINUTES = 30
DIFFERENT_TIME_MINUTES = 60
df = pd.read_csv(source_path, dtype="string", keep_default_na=False, low_memory=False)

# Submitter fields are shared by everyone in this export. A device is only a
# proxy for an interviewer, so output names and metadata explicitly say device.
interviews = df.drop_duplicates("KEY").copy()
interviews["device"] = interviews["deviceid"].str.strip()
interviews["local_day"] = interviews["start"].str.slice(0, 10)
interviews["timestamp"] = pd.to_datetime(interviews["start"], format="ISO8601", utc=True, errors="coerce")
interviews = interviews.sort_values(["device", "local_day", "timestamp", "KEY"])
interviews["day_sequence"] = interviews.groupby(["device", "local_day"]).cumcount()
sequence = interviews.set_index("KEY")["day_sequence"]

children = df.loc[df["child_KEY"].str.strip().ne("")].copy()
children["normalized_name"] = children["NameB"].str.normalize("NFKC").str.casefold().str.split().str.join(" ")
children["normalized_sex"] = children["sex"].str.strip().str.casefold()
# Compare calendar birthdates without shifting midnight to a different timezone.
children["normalized_dob"] = pd.to_datetime(
    children["dob"].str.strip().str.slice(0, 10), format="%Y-%m-%d", errors="coerce"
).dt.strftime("%Y-%m-%d")
children["timestamp"] = pd.to_datetime(children["start"], format="ISO8601", utc=True, errors="coerce")
children["local_day"] = children["start"].str.slice(0, 10)
children["device"] = children["deviceid"].str.strip()
children["day_sequence"] = children["KEY"].map(sequence)
placeholders = {"", "unknown", "na", "n/a", "none", "test", "999", "0", "no name", "unnamed", "not applicable"}
eligible = (
    ~children["normalized_name"].isin(placeholders)
    & children["normalized_dob"].notna()
    & children["normalized_sex"].isin(["male", "female"])
)
identities = ["normalized_name", "normalized_dob", "normalized_sex"]
candidates = children.loc[eligible]
repeated = candidates.loc[candidates.duplicated(identities, keep=False)]
flags = defaultdict(set)
group_ids = {}
pair_rows = []
child_records = repeated.to_dict(orient="index")
for number, (_, group) in enumerate(repeated.groupby(identities, sort=True), start=1):
    group_id = f"duplicate_child_{number:04d}"
    for first, second in combinations(group.index, 2):
        a, b = child_records[first], child_records[second]
        reasons = []
        delta = None
        if pd.notna(a["timestamp"]) and pd.notna(b["timestamp"]):
            delta = abs((a["timestamp"] - b["timestamp"]).total_seconds()) / 60
        if a["KEY"] == b["KEY"]:
            reasons.append("duplicate_child_within_household")
        elif a["device"] and b["device"] and delta is not None:
            if a["device"] == b["device"]:
                if a["local_day"] != b["local_day"]:
                    reasons.append("same_device_different_days")
                elif abs(a["day_sequence"] - b["day_sequence"]) == 1:
                    reasons.append("same_device_consecutive_interviews_same_day")
            elif delta <= SAME_TIME_MINUTES:
                reasons.append("different_devices_about_same_time")
            elif delta >= DIFFERENT_TIME_MINUTES:
                reasons.append("different_devices_at_least_one_hour_apart")
        if not reasons:
            continue
        for index in (first, second):
            flags[index].update(reasons)
            group_ids[index] = group_id
        pair_rows.append({
            "duplicate_group_id": group_id,
            "data_row_1": first + 1,
            "data_row_2": second + 1,
            "interview_KEY_1": a["KEY"],
            "interview_KEY_2": b["KEY"],
            "child_KEY_1": a["child_KEY"],
            "child_KEY_2": b["child_KEY"],
            "device_id_1": a["device"],
            "device_id_2": b["device"],
            "start_1": a["start"],
            "start_2": b["start"],
            "time_gap_minutes": delta,
            "flag_reasons": ";".join(reasons),
        })

flagged = df.loc[sorted(flags)].copy()
flagged.insert(0, "source_data_row", flagged.index + 1)
flagged["duplicate_group_id"] = [group_ids[index] for index in flagged.index]
flagged["flag_reasons"] = [";".join(sorted(flags[index])) for index in flagged.index]
flagged["identity_match_fields"] = "NameB + dob + sex"
flagged["interviewer_proxy_field"] = "deviceid (not verified interviewer identity)"
flagged["review_status"] = "needs_review"
pair_columns = [
    "duplicate_group_id", "data_row_1", "data_row_2", "interview_KEY_1",
    "interview_KEY_2", "child_KEY_1", "child_KEY_2", "device_id_1", "device_id_2",
    "start_1", "start_2", "time_gap_minutes", "flag_reasons",
]
pairs = pd.DataFrame(pair_rows, columns=pair_columns)
assert flagged["child_KEY"].is_unique
assert flagged["flag_reasons"].ne("").all()
assert set(pairs["child_KEY_1"]) | set(pairs["child_KEY_2"]) == set(flagged["child_KEY"])
flagged_path = source_path.with_name("Interview_1_merged_cleaned_flagged.csv")
pairs_path = source_path.with_name("Interview_1_flagged_duplicate_pairs.csv")
flagged.to_csv(flagged_path, index=False)
pairs.to_csv(pairs_path, index=False)
print(f"Child rows eligible for name + DOB + sex matching: {len(candidates):,} / {len(children):,}")
print(f"Flagged child rows: {len(flagged):,}")
print(f"Affected interviews: {flagged['KEY'].nunique():,}")
print(f"Flagged duplicate groups: {flagged['duplicate_group_id'].nunique():,}")
print(f"Flagged pairs: {len(pairs):,}")
for reason in sorted({reason for reasons in flags.values() for reason in reasons}):
    print(f"{reason}: {sum(reason in reasons for reasons in flags.values()):,} rows")
print(f"\nFlagged rows: {flagged_path.name}")
print(f"Pair evidence: {pairs_path.name}")
print("Missing identity fields, same-device nonconsecutive same-day repeats, and different-device gaps >30 but <60 minutes are not flagged by these rules.")
