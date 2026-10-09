from pathlib import Path
from collections import Counter
from itertools import combinations
import csv
import re
import pandas as pd

base_dir = Path(__file__).resolve().parent

file_path = base_dir / "Interview_1(in).csv"

df = pd.read_csv(file_path, low_memory=False, dtype="string", keep_default_na=False)

#print(df.columns.tolist())

# Check the original header: pandas renames repeated headers automatically.
with file_path.open(newline="", encoding="utf-8-sig") as source:
    header = next(csv.reader(source))
duplicates = [name for name, count in Counter(header).items() if count > 1]

if duplicates:
    print("Duplicate column names:", duplicates)
else:
    print("No identical column names found.")

# A numbered suffix suggests a related column; it does not prove duplication.
# Handles hoh_name1, hoh_name_1, and pandas-renamed headers such as hoh_name.1.
pairs = []
for column in df.columns:
    base = re.sub(r"[._]?\d+$", "", column)
    if base != column and base in df.columns:
        pairs.append((base, column))

differences = []
for base, variant in pairs:
    left = df[base].str.strip()
    right = df[variant].str.strip()
    left_present = left.ne("")
    right_present = right.ne("")
    left_only = left_present & ~right_present
    right_only = right_present & ~left_present
    conflicting = left_present & right_present & left.ne(right)
    matching = left_present & right_present & left.eq(right)

    # Also compare values across the entire columns, independent of row position.
    left_values = set(left[left_present])
    right_values = set(right[right_present])
    print(f"\n{base} vs {variant}:")
    print(f"  Rows populated only in {base}: {left_only.sum()}")
    print(f"  Rows populated only in {variant}: {right_only.sum()}")
    print(f"  Rows with different nonblank values: {conflicting.sum()}")
    print(f"  Rows with matching nonblank values: {matching.sum()}")
    print(f"  Distinct values found only in {base}: {len(left_values - right_values)}")
    print(f"  Distinct values found only in {variant}: {len(right_values - left_values)}")

    mask = left_only | right_only | conflicting
    detail = pd.DataFrame({
        "data_row": df.index[mask] + 1,
        "base_column": base,
        "variant_column": variant,
        "base_value": df.loc[mask, base].to_numpy(),
        "variant_value": df.loc[mask, variant].to_numpy(),
        "difference": [
            "base_only" if left_only.loc[index] else
            "variant_only" if right_only.loc[index] else "different_values"
            for index in df.index[mask]
        ],
        "base_value_absent_from_variant": (~left[mask].isin(right_values) & left_present[mask]).to_numpy(),
        "variant_value_absent_from_base": (~right[mask].isin(left_values) & right_present[mask]).to_numpy(),
    })
    differences.append(detail)

if differences:
    report_path = file_path.with_name(f"{file_path.stem}_column_differences.csv")
    pd.concat(differences, ignore_index=True).to_csv(report_path, index=False)
    print(f"\nDifference details saved to: {report_path.name}")
    print("data_row is 1-based and excludes the header; surrounding whitespace is ignored.")
else:
    print("No numbered column variants found.")

# Compare every pair in each numbered family, including numbered siblings
# even when there is no unnumbered column (e.g. mother_name_present_1 / _2).
groups = {}
for column in df.columns:
    base = re.sub(r"[._]?\d+$", "", column)
    if base != column:
        groups.setdefault(base, []).append(column)

overlap_rows = []
group_rows = []
for base, numbered_columns in groups.items():
    columns = ([base] if base in df.columns else []) + numbered_columns
    if len(columns) < 2:
        continue
    values = df[columns].apply(lambda column: column.str.strip())
    populated = values.ne("")
    populated_count = populated.sum(axis=1)
    group_rows.append({
        "column_family": base,
        "columns": ", ".join(columns),
        "rows_with_any_value": int(populated_count.ge(1).sum()),
        "rows_with_multiple_columns_populated": int(populated_count.ge(2).sum()),
        "rows_with_all_columns_populated": int(populated_count.eq(len(columns)).sum()),
        "rows_with_all_columns_matching": int(
            (populated_count.eq(len(columns)) & values.eq(values.iloc[:, 0], axis=0).all(axis=1)).sum()
        ),
    })
    for first, second in combinations(columns, 2):
        both = populated[first] & populated[second]
        matching = both & values[first].eq(values[second])
        first_values = set(values.loc[populated[first], first])
        second_values = set(values.loc[populated[second], second])
        overlap_rows.append({
            "column_family": base,
            "column_1": first,
            "column_2": second,
            "column_1_populated_rows": int(populated[first].sum()),
            "column_2_populated_rows": int(populated[second].sum()),
            "both_populated_rows": int(both.sum()),
            "matching_value_rows": int(matching.sum()),
            "different_value_rows": int((both & ~matching).sum()),
            "shared_distinct_values": len(first_values & second_values),
        })

if overlap_rows:
    overlap_summary = pd.DataFrame(overlap_rows)
    group_summary = pd.DataFrame(group_rows)
    print("\nNumbered column overlaps (blank values excluded):")
    print(overlap_summary.to_string(index=False))
    for suffix, summary in (("column_overlaps", overlap_summary),
                            ("column_family_overlaps", group_summary)):
        output_path = file_path.with_name(f"{file_path.stem}_{suffix}.csv")
        summary.to_csv(output_path, index=False)
        print(f"\nOverlap summary saved to: {output_path.name}")

# Coalesce only families with no conflicting nonblank values on any row.
# Prefer the unnumbered column, then variants in original file order.
# Keep the original cell text; trimming is used only to compare/find blanks.
conflicting_families = {
    row["column_family"] for row in overlap_rows
    if row["different_value_rows"] > 0
}
cleaned = df.copy()
merged_families = []
for base, numbered_columns in groups.items():
    columns = ([base] if base in df.columns else []) + numbered_columns
    if len(columns) < 2 or base in conflicting_families:
        continue
    merged = df[columns[0]].copy()
    for column in columns[1:]:
        fill = merged.str.strip().eq("") & df[column].str.strip().ne("")
        merged.loc[fill] = df.loc[fill, column]

    # Every populated source value must survive in the merged column.
    for column in columns:
        populated = df[column].str.strip().ne("")
        assert merged[populated].str.strip().eq(df.loc[populated, column].str.strip()).all()

    if base in cleaned.columns:
        cleaned[base] = merged
    else:
        position = cleaned.columns.get_loc(columns[0])
        cleaned.insert(position, base, merged)
    cleaned.drop(columns=numbered_columns, inplace=True)
    merged_families.append(base)

assert len(cleaned) == len(df)
for column in cleaned.columns:
    if column not in merged_families:
        assert cleaned[column].equals(df[column])

cleaned_path = file_path.with_name(f"{file_path.stem}_cleaned.csv")
cleaned.to_csv(cleaned_path, index=False)
print(f"\nCleaned file saved to: {cleaned_path.name}")
print(f"Rows retained: {len(cleaned)}; columns: {len(df.columns)} -> {len(cleaned.columns)}")
print("Merged families:", ", ".join(merged_families))
print("Conflicting families kept separate:", ", ".join(sorted(conflicting_families)))
