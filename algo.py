from datetime import datetime, timedelta

def calculate_overlap(slots_by_participant: dict, duration_minutes: int = 30) -> list:
    participants = list(slots_by_participant.keys())
    
    if not participants:
        return []

    common_slots = []
    for slot in slots_by_participant[participants[0]]:
        common_slots.append({
            "start": datetime.fromisoformat(slot["start"]),
            "end": datetime.fromisoformat(slot["end"])
        })

    for p in participants[1:]:
        new_common_slots = []
        for common in common_slots:
            for p_slot in slots_by_participant[p]:
                p_start = datetime.fromisoformat(p_slot["start"])
                p_end = datetime.fromisoformat(p_slot["end"])

                overlap_start = max(common["start"], p_start)
                overlap_end = min(common["end"], p_end)

                if overlap_start < overlap_end:
                    duration = (overlap_end - overlap_start).total_seconds() / 60
                    if duration >= duration_minutes:
                        new_common_slots.append({
                            "start": overlap_start,
                            "end": overlap_end
                        })
        
        common_slots = new_common_slots

    formatted_results = []
    for i, slot in enumerate(common_slots):
        # We slice the slot to exactly our required duration from the start time
        exact_end = slot["start"] + timedelta(minutes=duration_minutes)
        formatted_results.append({
            "preference": i + 1,
            "start": slot["start"].isoformat(),
            "end": exact_end.isoformat()
        })

    return formatted_results

if __name__ == "__main__":
    mock_data = {
        "Host_User": [
            {"start": "2026-04-10T09:00:00", "end": "2026-04-10T12:00:00"},
            {"start": "2026-04-10T14:00:00", "end": "2026-04-10T17:00:00"}
        ],
        "Participant_A": [
            {"start": "2026-04-10T10:30:00", "end": "2026-04-10T11:30:00"}, 
            {"start": "2026-04-10T15:00:00", "end": "2026-04-10T16:00:00"}  
        ],
        "Participant_B": [
            {"start": "2026-04-10T11:00:00", "end": "2026-04-10T13:00:00"},
            {"start": "2026-04-10T14:30:00", "end": "2026-04-10T15:45:00"}  
        ]
    }

    print("Running CalSync Overlap Algorithm...")
    results = calculate_overlap(mock_data, duration_minutes=30)
    
    if results:
        print("\n✅ Success! Found the following valid 30-minute slots:")
        for res in results:
            print(f"Option {res['preference']}: {res['start']} to {res['end']}")
    else:
        print("\n❌ No overlapping slots found.")