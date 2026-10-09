"""Clean nonoverlapping base/1 child columns and join children to interviews."""

from pathlib import Path
import re

import pandas as pd


base_dir = Path(__file__).resolve().parent
interview_path = base_dir / "Interview_1(in)_cleaned.csv"
child_path = base_dir / "Interview_1-child_repeat(in).csv"
read_options = {"dtype": "string", "keep_default_na": False, "low_memory": False}
interviews = pd.read_csv(interview_path, **read_options)
children = pd.read_csv(child_path, **read_options)
cleaned_children = children.copy()
audit = []

# Only merge a base with its trailing-1 variant; do not merge siblings or
# other numbered columns. Even matching values count as overlapping entries.
for variant in children.columns:
    match = re.fullmatch(r"(.+?)[._]?1", variant)
    if match is None or match[1] not in children.columns:
        continue
    base = match[1]
    left = children[base].str.strip()
    right = children[variant].str.strip()
    both = left.ne("") & right.ne("")
    overlap_count = int(both.sum())
    audit.append({
        "base_column": base,
        "variant_column": variant,
        "base_populated_rows": int(left.ne("").sum()),
        "variant_populated_rows": int(right.ne("").sum()),
        "overlapping_rows": overlap_count,
        "conflicting_rows": int((both & left.ne(right)).sum()),
        "action": "merged" if overlap_count == 0 else "kept_separate",
    })
    if overlap_count:
        continue
    merged = children[base].copy()
    fill = left.eq("") & right.ne("")
    merged.loc[fill] = children.loc[fill, variant]
    for column in (base, variant):
        populated = children[column].str.strip().ne("")
        assert merged[populated].equals(children.loc[populated, column])
    cleaned_children[base] = merged
    cleaned_children.drop(columns=variant, inplace=True)

audit_df = pd.DataFrame(audit, columns=[
    "base_column", "variant_column", "base_populated_rows",
    "variant_populated_rows", "overlapping_rows", "conflicting_rows", "action",
])
assert len(cleaned_children) == len(children)
for column in cleaned_children.columns:
    if column not in set(audit_df.loc[audit_df["action"].eq("merged"), "base_column"]):
        assert cleaned_children[column].equals(children[column])

# Validate linkage before writing outputs; blank keys cannot identify a record.
if interviews["KEY"].str.strip().eq("").any() or interviews["KEY"].duplicated().any():
    raise ValueError("Interview KEY must be populated and unique.")
if cleaned_children["PARENT_KEY"].str.strip().eq("").any():
    raise ValueError("Child PARENT_KEY must be populated.")
if cleaned_children["KEY"].str.strip().eq("").any() or cleaned_children["KEY"].duplicated().any():
    raise ValueError("Child KEY must be populated and unique.")

# Keep interview names intact and explicitly label colliding child columns.
renames = {
    column: f"child_{column}" for column in cleaned_children.columns
    if column in interviews.columns
}
child_for_join = cleaned_children.rename(columns=renames)
if not child_for_join.columns.is_unique or set(renames.values()) & set(interviews.columns):
    raise ValueError("Renaming shared child columns would create duplicate names.")

# Full outer join retains interviews without children and any orphan children.
# Each child remains one row; interview details repeat for multiple children.
merged = interviews.merge(
    child_for_join,
    left_on="KEY",
    right_on="PARENT_KEY",
    how="outer",
    validate="one_to_many",
    indicator="record_link_status",
    sort=False,
)
merged["record_link_status"] = merged["record_link_status"].cat.rename_categories({
    "left_only": "interview_without_child",
    "right_only": "child_without_interview",
    "both": "matched",
})
child_key_column = renames.get("KEY", "KEY")
child_rows = merged[child_key_column].notna()
assert int(child_rows.sum()) == len(children)
assert set(merged.loc[child_rows, child_key_column]) == set(children["KEY"])
assert set(merged["KEY"].dropna()) == set(interviews["KEY"])
assert not merged.loc[child_rows, child_key_column].duplicated().any()

cleaned_child_path = child_path.with_name(f"{child_path.stem}_cleaned.csv")
audit_path = child_path.with_name(f"{child_path.stem}_cleaning_report.csv")
merged_path = base_dir / "Interview_1_merged_cleaned.csv"
cleaned_children.to_csv(cleaned_child_path, index=False)
audit_df.to_csv(audit_path, index=False)
merged.to_csv(merged_path, index=False)
print(audit_df.to_string(index=False))
print(f"\nChild rows retained: {len(cleaned_children):,}")
print(f"Interview rows before join: {len(interviews):,}")
print(f"Merged rows: {len(merged):,}; columns: {len(merged.columns)}")
print(merged["record_link_status"].value_counts().to_string())
print("Shared child columns renamed:", renames)
print(f"\nCleaned child file: {cleaned_child_path.name}")
print(f"Cleaning report: {audit_path.name}")
print(f"Merged file: {merged_path.name}")
