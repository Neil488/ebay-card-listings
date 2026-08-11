# Scheduled eBay upload cadence

## Goal
Add configurable scheduling so generated eBay CSV listings do not go live immediately and are staggered over days.
Also add storage group tagging in listing notes and custom labels.

## Decisions
- Keep defaults in script-level config for simplicity.
- Use AEST fixed offset (UTC+10) per request.
- Default cadence: 3 listings/day at 17:00 AEST.
- If current AEST time is past today's target time, start scheduling from tomorrow.

## Progress
- [x] Capture requirements
- [x] Implement scheduling config + schedule generator
- [x] Wire ScheduleTime per row
- [x] Validate script execution

## Open items
- Confirm whether multiple listings at the same 17:00 time is acceptable, or if intra-day staggering (e.g., 17:00/17:10/17:20) is preferred.

## Validation snapshot
- Script run completed successfully with 12 cards.
- Generated cadence was 3 listings/day at 17:00 AEST across 4 days.
- Group tag applied as `Group: AB5` in `AdditionalDetails`.
- `CustomLabel` was prefixed with `AB5-` for each listing.
