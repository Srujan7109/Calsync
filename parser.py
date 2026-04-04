import spacy
import dateparser
import pytz
from datetime import datetime

nlp = spacy.load("en_core_web_sm")

def extract_time_slots(text: str, user_timezone: str = "UTC") -> list:
    doc = nlp(text)
    
    time_entities = [ent.text for ent in doc.ents if ent.label_ in ("TIME", "DATE")]
    
    if not time_entities:
        return []

    parsed_slots = []
    
    settings = {
        'TIMEZONE': user_timezone, 
        'RETURN_AS_TIMEZONE_AWARE': True,
        'TO_TIMEZONE': 'UTC', 
        'PREFER_DATES_FROM': 'future'
    }

    for ent_text in time_entities:
        try:
            parsed_dt = dateparser.parse(ent_text, settings=settings)
            
            if parsed_dt:
                start_time = parsed_dt
                end_time = start_time.replace(hour=start_time.hour + 1) if start_time.hour < 23 else start_time
                
                parsed_slots.append({
                    "extracted_phrase": ent_text,
                    "start": start_time.isoformat(),
                    "end": end_time.isoformat()
                })
        except Exception as e:
            print(f"Failed to parse entity '{ent_text}': {e}")
            continue

    return parsed_slots

if __name__ == "__main__":
    sample_email_text = "Hey! I can't do today, but I am free tomorrow at 2 PM or next Tuesday at 9:30 AM."
    sender_tz = "Asia/Kolkata" # IST

    print(f"Analyzing text: '{sample_email_text}'")
    print(f"Sender Timezone: {sender_tz}\n")
    
    results = extract_time_slots(sample_email_text, user_timezone=sender_tz)
    
    if results:
        print("✅ Extracted & Normalized Slots (Converted to UTC):")
        for res in results:
            print(f"- Phrase caught: '{res['extracted_phrase']}' -> Start UTC: {res['start']}")
    else:
        print("❌ No valid time slots found.")