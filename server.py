from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Dict, List, Optional, Any

# Import the core logic functions we just built
from parser import extract_time_slots
from algo import calculate_overlap

app = FastAPI(title="CalSync Compute & NLP MCP", version="1.0")


class ParseRequest(BaseModel):
    text: str
    timezone: str = "UTC"
    reference_date: Optional[str] = None

class OverlapRequest(BaseModel):
    slots_by_participant: Dict[str, List[Dict[str, str]]]
    duration_minutes: int = 30
    priority_weights: Optional[Dict[str, int]] = None 


@app.get("/")
def health_check():
    return {"status": "Compute & NLP MCP is running on port 8001"}

@app.post("/parse_availability")
@app.post("/mcp/compute/parse_availability")
def api_parse_availability(request: ParseRequest):
    try:
        results = extract_time_slots(
            text=request.text, 
            user_timezone=request.timezone
        )
        
        if not results:
            return {
                "status": "AMBIGUOUS", 
                "confidence": 0.0, 
                "message": f"Could not determine specific times from: '{request.text}'"
            }
            
        return {"status": "OK", "slots": results}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/compute_overlap")
@app.post("/mcp/compute/compute_overlap")
def api_compute_overlap(request: OverlapRequest):
    try:
        results = calculate_overlap(
            slots_by_participant=request.slots_by_participant,
            duration_minutes=request.duration_minutes
        )
        
        if not results:
            return {
                "status": "NO_OVERLAP", 
                "suggestion": "Ask participants for more slots"
            }
            
        return {"status": "OK", "overlapping_slots": results}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)