Image transcription:

- Interview to drop:
  - Apparently falsified interviews, based on suspicious card photos identified in stage 1
  - Duplicate information about the same child within a single household interview
  - Records logged by the same interviewer, one after another on the same day
  - Records logged by the same interviewer across different days
  - Records logged by different interviews at about the same time
  - Records logged by different interviewers at different times (separated by hours or days)

The image literally says “different interviews” in the fifth item; this is
interpreted as “different interviewers” for the initial checks.

Initial implementation:

- Photo-based checks are excluded, as requested.
- Every check requires repeated child information: normalized NameB, a valid
  calendar date in dob, and matching sex. Blank/placeholder names and missing
  DOB or sex are excluded. dob1 is not used to fill dob.
- Name normalization ignores case, repeated whitespace, and Unicode width differences.
- Within-household duplicates require the same interview KEY and distinct child_KEYs.
- Interviewer identity is unavailable: SubmitterID and SubmitterName are constant.
  deviceid is used only as a labeled proxy; shared devices or multiple devices
  per interviewer can affect classifications.
- Interview start is the event time. Same-day checks use the date as recorded
  in start; elapsed-time comparisons account for timezone offsets.
- “One after another” means adjacent interviews in the device's chronological
  sequence on that day, including interviews with no child record.
- “About the same time” means a gap of at most 30 minutes.
- Different times separated by hours or days means a gap of at least 60 minutes.
- Same-device nonconsecutive same-day repeats and different-device gaps strictly
  between 30 and 60 minutes do not meet these initial rules.
- Only implicated child rows enter the flagged dataset; other children in an
  affected household are not automatically flagged. Both sides of each qualifying
  duplicate pair are included. Source rows are never deleted.
- Flags identify review candidates, not confirmed duplicates or falsified interviews.
- source_data_row is 1-based within Interview_1_merged_cleaned.csv, excluding its header.
- The pair evidence file lists the counterpart record and reason for each flag.
