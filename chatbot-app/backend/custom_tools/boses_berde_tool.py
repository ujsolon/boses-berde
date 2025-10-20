# boses_berde_tool.py
"""
Boses Berde Agent - Main conversational/triage agent for Job/Training/recruitment flows.
"""

import asyncio
import json
import logging
import os
import uuid
from typing import Any, Dict, List, Optional

from strands import tool
from utils.customer_utils import get_selected_customer_id, run_async

# Try to import tool events channel if present (same pattern as template)
try:
    from routers.tool_events import tool_events_channel
    ANALYSIS_CHANNEL_AVAILABLE = tool_events_channel is not None
except Exception:
    tool_events_channel = None
    ANALYSIS_CHANNEL_AVAILABLE = False

logger = logging.getLogger(__name__)

# Attempt to import the strands http_request tool (if installed as a tool)
# Fallback to requests if not available. We keep calls wrapped so agent still works offline.
try:
    from strands_tools.http_request import http_request as strands_http_request
    HAS_STRANDS_HTTP = True
except Exception:
    strands_http_request = None
    HAS_STRANDS_HTTP = False

# Attempt to import a visualization tool (if available)
try:
    from strands_tools.visualization import visualization_tool
    HAS_VIS_TOOL = True
except Exception:
    visualization_tool = None
    HAS_VIS_TOOL = False

# --- MCP endpoints (user-provided) ---
MCP_ENDPOINTS = {
    "training_finder": {
        "api_url": "https://782hmar34c.execute-api.us-west-2.amazonaws.com/prod/mcp",
        "ssm_param": "/mcp/endpoints/serverless/training-finder",
    },
    "job_finder": {
        "api_url": "https://s8vwgvg73g.execute-api.us-west-2.amazonaws.com/prod/mcp",
        "ssm_param": "/mcp/endpoints/serverless/job-finder",
    },
    # recruiter details not provided yet; keep placeholder
    "recruiter_insights": {
        "api_url": None,
        "ssm_param": "/mcp/endpoints/serverless/recruiter-insights",
    },
}

# --- Mock data for local testing without persistence ---
MOCK_USERS = {
    "u_local_1": {
        "id": "u_local_1",
        "first_name": "Ana",
        "last_name": "Cruz",
        "age": 22,
        "education": "Bachelor's - IT",
        "interests": ["web development", "data", "frontend"],
        "location": "Manila",
        "preferences": {"remote": True},
    },
    "u_local_2": {
        "id": "u_local_2",
        "first_name": "Carlos",
        "last_name": "Dela Vega",
        "age": 27,
        "education": "Diploma - Hospitality",
        "interests": ["customer service", "training"],
        "location": "Cebu",
        "preferences": {"remote": False},
    },
}

MOCK_JOBS = [
    {"id": "job_101", "title": "Junior Frontend Dev", "remote": True, "skills": ["javascript", "react"], "location": "Remote"},
    {"id": "job_102", "title": "IT Support Technician", "remote": False, "skills": ["helpdesk"], "location": "Manila"},
    {"id": "job_103", "title": "Customer Service Rep", "remote": False, "skills": ["customer service"], "location": "Cebu"},
]

MOCK_TRAININGS = [
    {"id": "tr_201", "title": "Frontend Web Bootcamp", "provider": "TechAcademy PH", "mode": "remote", "schedule": "Mon-Fri 6-9pm", "register_url": "https://example.com/training/frontend"},
    {"id": "tr_202", "title": "Hotel Reception Basics", "provider": "Tourism Institute", "mode": "in-person", "schedule": "Weekends", "location": "Cebu", "register_url": "https://example.com/training/hospitality"},
    {"id": "tr_203", "title": "Data Fundamentals", "provider": "OpenLearn", "mode": "remote", "schedule": "Self-paced", "register_url": "https://example.com/training/data"},
]


# ---------------- Helper utilities ---------------- #
def _safe_session_id() -> str:
    try:
        from utils.tool_execution_context import get_current_session_id
        sid = get_current_session_id()
        if sid:
            return sid
    except Exception:
        pass
    return f"bosesberde_{uuid.uuid4().hex[:8]}"


async def _send_progress(tool_name: str, session_id: str, status: str, message: str, progress: Optional[int] = None, meta: Optional[Dict] = None):
    if ANALYSIS_CHANNEL_AVAILABLE and tool_events_channel:
        try:
            await tool_events_channel.send_progress(tool_name, session_id, status, message, progress, meta or {})
        except Exception as e:
            logger.debug("Failed to send progress update: %s", e)


def _simple_user_profile_from_mock(user_id: str) -> Optional[Dict]:
    return MOCK_USERS.get(user_id)


# Try to use strands http_request tool if available; else fallback to requests
def _http_get(url: str, params: Dict = None, headers: Dict = None, timeout: int = 10) -> Dict:
    params = params or {}
    headers = headers or {}
    if HAS_STRANDS_HTTP and strands_http_request:
        # strands_http_request might expect a dict input; adapt conservatively
        try:
            resp = strands_http_request("GET", url, params=params, headers=headers, timeout=timeout)
            # If it's a tool that returns a dict-like response
            return resp
        except Exception as e:
            logger.warning("strands_http_request failed: %s - falling back to requests", e)
    # fallback to requests
    try:
        import requests
        r = requests.get(url, params=params, headers=headers, timeout=timeout)
        try:
            return {"status_code": r.status_code, "body": r.json()}
        except Exception:
            return {"status_code": r.status_code, "body": r.text}
    except Exception as e:
        logger.error("HTTP GET failed: %s", e)
        return {"status_code": None, "error": str(e)}


# ---------------- Core agent logic ---------------- #
@tool
def boses_berde(user_id: str = None, gather_info: bool = True) -> str:
    """
    Main Boses Berde agent tool.

    Flows:
      1. Overview
      2. Gather user info (if gather_info True)
      3. Triage: which MCP is needed (job/training/recruiter)
      4. Check MCP availability (ping)
      5. Fetch stats from MCPs
      6. Attempt a simple match using MCP (or local mock if MCP unreachable)

    Args:
        user_id: optional local user id for MOCK_USERS
        gather_info: whether to run the info-gathering flow (set False to skip)

    Returns:
        str: Text summary (markdown-like) of results
    """

    async def _boses_berde_async():
        session_id = _safe_session_id()
        tool_name = "boses_berde_tool"
        try:
            await _send_progress(tool_name, session_id, "started", "Boses Berde agent started", 5, {"user_id": user_id})

            # 1) Project overview
            overview = (
                "# Boses Berde — Job & Training Matchmaker\n\n"
                "I help Filipinos (especially youth) find jobs and training opportunities. "
                "I can:\n"
                "- explain what this project does\n"
                "- gather your info and preferences\n"
                "- check which backend MCP server to call (job, training, recruiter insights)\n"
                "- fetch statistics and match you to job or training opportunities\n"
            )

            await _send_progress(tool_name, session_id, "progress", "Overview provided", 10)

            # 2) Gather user info (mocked or from provided id)
            if gather_info and user_id:
                user_profile = _simple_user_profile_from_mock(user_id)
                if not user_profile:
                    user_profile = {
                        "id": user_id,
                        "first_name": "Guest",
                        "last_name": "",
                        "age": None,
                        "education": None,
                        "interests": [],
                        "location": None,
                        "preferences": {},
                    }
                    logger.debug("No mock user found; using empty profile")
            elif gather_info and not user_id:
                # No persistence and no provided user id: create ephemeral guest profile
                user_profile = {
                    "id": f"guest_{uuid.uuid4().hex[:6]}",
                    "first_name": "Guest",
                    "last_name": "",
                    "age": None,
                    "education": None,
                    "interests": [],
                    "location": None,
                    "preferences": {},
                }
            else:
                user_profile = None

            await _send_progress(tool_name, session_id, "progress", "User info gathered", 20, {"profile_exists": bool(user_profile)})

            # 3) Triage logic: decide which MCP is likely needed
            # Simple heuristic: if user indicates interests that match job skills -> job_finder.
            # If interests include "training" or education is low -> training_finder.
            triage = {"selected_mcp": None, "reason": None}

            if user_profile:
                interests = [i.lower() for i in (user_profile.get("interests") or [])]
                education = (user_profile.get("education") or "").lower()
                prefs = user_profile.get("preferences") or {}

                if any("train" in i or "course" in i or "bootcamp" in i for i in interests) or "diploma" in education or "high school" in education:
                    triage["selected_mcp"] = "training_finder"
                    triage["reason"] = "User has training-oriented interests or lower formal education"
                elif any(skill in ["javascript", "react", "helpdesk", "customer service", "data"] for skill in interests):
                    triage["selected_mcp"] = "job_finder"
                    triage["reason"] = "Interests match job skills"
                else:
                    # default: show both options, prefer training for youth
                    triage["selected_mcp"] = "training_finder"
                    triage["reason"] = "Default to training finder for youth upskilling"
            else:
                triage["selected_mcp"] = "training_finder"
                triage["reason"] = "No profile provided; default to training"

            await _send_progress(tool_name, session_id, "progress", f"Triage decided: {triage['selected_mcp']}", 30, triage)

            # 4) Check MCP availability (ping)
            # Ping job/training endpoints and collect statuses
            ping_results = {}
            for key, meta in MCP_ENDPOINTS.items():
                api_url = meta.get("api_url")
                if not api_url:
                    ping_results[key] = {"available": False, "note": "No API URL configured"}
                    continue
                # Use a lightweight GET to root/mcp/ping or the provided base endpoint
                ping_url = api_url
                try:
                    resp = _http_get(ping_url, params={"op": "ping"}, timeout=6)
                    status_code = resp.get("status_code")
                    if status_code and int(status_code) < 400:
                        ping_results[key] = {"available": True, "status_code": status_code}
                    else:
                        ping_results[key] = {"available": False, "status_code": status_code, "body": resp.get("body")}
                except Exception as e:
                    ping_results[key] = {"available": False, "error": str(e)}

            await _send_progress(tool_name, session_id, "progress", "MCP ping completed", 45, {"ping_summary": ping_results})

            # 5) Fetch some statistics from the chosen MCP (if available)
            selected = triage["selected_mcp"]
            stats = None
            fetch_note = None
            if MCP_ENDPOINTS.get(selected, {}).get("api_url"):
                api_url = MCP_ENDPOINTS[selected]["api_url"]
                try:
                    # Example call: ask the MCP for summary statistics
                    resp = _http_get(api_url, params={"op": "summary"}, timeout=8)
                    if resp.get("status_code") and int(resp.get("status_code")) < 400:
                        stats = resp.get("body")
                        fetch_note = "Fetched stats from MCP"
                    else:
                        fetch_note = "MCP returned non-OK; falling back to local mock stats"
                except Exception as e:
                    fetch_note = f"Failed to fetch MCP stats: {e}; using local mock stats"
            else:
                fetch_note = "No API for selected MCP; using local mock stats"

            if not stats:
                # Construct simple mock stats
                stats = {
                    "total_jobs": len(MOCK_JOBS),
                    "total_trainings": len(MOCK_TRAININGS),
                    "recent_hires": 5,
                    "popular_skills": ["javascript", "react", "customer service"],
                }

            await _send_progress(tool_name, session_id, "progress", "Statistics collected", 65, {"stats_preview": stats})

            # 6) Attempt matching: call MCP matching endpoints if available; else use local mock matching
            matches = []
            match_note = None
            if MCP_ENDPOINTS.get(selected, {}).get("api_url") and ping_results.get(selected, {}).get("available"):
                # Example: try a match call
                match_url = MCP_ENDPOINTS[selected]["api_url"]
                try:
                    resp = _http_get(match_url, params={"op": "match", "profile_id": user_profile.get("id") if user_profile else "guest"}, timeout=10)
                    if resp.get("status_code") and int(resp.get("status_code")) < 400:
                        matches = resp.get("body")
                        match_note = "Matches returned by MCP"
                    else:
                        match_note = "MCP match returned non-OK; computing local matches"
                except Exception as e:
                    match_note = f"MCP match call failed: {e}; using local matching"
            else:
                match_note = "MCP not available; running local matching"

            if not matches:
                # local matching heuristics
                matches = []
                if selected == "job_finder":
                    # match by intersection of interests and job skills
                    user_skills = set([s.lower() for s in (user_profile.get("interests") or [])])
                    for job in MOCK_JOBS:
                        job_skills = set([s.lower() for s in job.get("skills", [])])
                        score = len(user_skills & job_skills)
                        if score > 0 or (user_profile and user_profile.get("preferences", {}).get("remote") is True and job.get("remote")):
                            matches.append({"job": job, "score": score})
                else:
                    # training finder: match by interest keywords, location, and mode
                    user_interests = set([s.lower() for s in (user_profile.get("interests") or [])]) if user_profile else set()
                    for tr in MOCK_TRAININGS:
                        score = 0
                        title_lower = tr.get("title", "").lower()
                        if any(i in title_lower for i in user_interests):
                            score += 2
                        if user_profile and user_profile.get("location") and tr.get("location") and user_profile.get("location").lower() == tr.get("location").lower():
                            score += 1
                        if user_profile and user_profile.get("preferences", {}).get("remote") and tr.get("mode") == "remote":
                            score += 1
                        if score > 0:
                            matches.append({"training": tr, "score": score})
                # sort by score desc
                matches = sorted(matches, key=lambda x: x.get("score", 0), reverse=True)
                match_note = match_note or "Local matches computed"

            await _send_progress(tool_name, session_id, "progress", "Matching completed", 85, {"matches_count": len(matches), "match_note": match_note})

            # (Optional) Use visualization tool to prepare a small summary chart (if available)
            viz_note = None
            if HAS_VIS_TOOL and visualization_tool:
                try:
                    # create a tiny bar summary of top categories (mock)
                    summary_for_viz = {
                        "total_jobs": stats.get("total_jobs"),
                        "total_trainings": stats.get("total_trainings"),
                        "recent_hires": stats.get("recent_hires", 0),
                    }
                    # call visualization tool in a safe way (it may be a tool; calling as function)
                    visualization_tool("Boses Berde Summary", summary_for_viz)
                    viz_note = "Visualization generated"
                except Exception as e:
                    viz_note = f"Visualization failed: {e}"
            else:
                viz_note = "No visualization tool available"

            # Build output summary
            output = {
                "overview": overview,
                "session_id": session_id,
                "user_profile": user_profile,
                "triage": triage,
                "ping_results": ping_results,
                "stats": stats,
                "matches": matches,
                "notes": {
                    "fetch_note": fetch_note,
                    "match_note": match_note,
                    "viz_note": viz_note,
                },
            }

            await _send_progress(tool_name, session_id, "completed", "Boses Berde task completed", 100, {"summary_keys": list(output.keys())})
            return json.dumps(output, indent=2, ensure_ascii=False)

        except Exception as e:
            logger.error(f"Error in boses_berde tool: {str(e)}", exc_info=True)
            if ANALYSIS_CHANNEL_AVAILABLE and tool_events_channel:
                try:
                    await tool_events_channel.send_progress(tool_name, session_id, "error", f"Error: {e}", None, {})
                except Exception:
                    pass
            return f"Error running Boses Berde agent: {str(e)}"

    return run_async(_boses_berde_async())


# Optional helper tools for unit testing or manual invocation
@tool
def ping_mcp(name: str) -> str:
    """
    Ping an MCP by name (training_finder, job_finder, recruiter_insights)
    Returns a brief JSON summary.
    """
    async def _ping_async():
        session_id = _safe_session_id()
        try:
            meta = MCP_ENDPOINTS.get(name)
            if not meta:
                return json.dumps({"error": "Unknown MCP name"}, indent=2)
            api_url = meta.get("api_url")
            if not api_url:
                return json.dumps({"available": False, "note": "No API URL configured"}, indent=2)
            resp = _http_get(api_url, params={"op": "ping"}, timeout=6)
            return json.dumps({"name": name, "api_url": api_url, "resp": resp}, indent=2)
        except Exception as e:
            return json.dumps({"error": str(e)}, indent=2)
    return run_async(_ping_async())


@tool
def fetch_stats_from_mcp(name: str) -> str:
    """
    Fetch 'summary' stats from given MCP. Useful for quick checks.
    """
    async def _fetch_async():
        try:
            meta = MCP_ENDPOINTS.get(name)
            if not meta or not meta.get("api_url"):
                return json.dumps({"error": "No API configured for this MCP"}, indent=2)
            resp = _http_get(meta["api_url"], params={"op": "summary"}, timeout=8)
            return json.dumps({"name": name, "resp": resp}, indent=2)
        except Exception as e:
            return json.dumps({"error": str(e)}, indent=2)
    return run_async(_fetch_async())


@tool
def match_user_to_opportunities(user_id: str, mcp: str = "training_finder") -> str:
    """
    Run local matching (or attempt MCP match) for a given user id.
    """
    async def _match_async():
        try:
            user_profile = _simple_user_profile_from_mock(user_id) or {"id": user_id, "interests": []}
            selected = mcp
            # Attempt MCP match if available
            if MCP_ENDPOINTS.get(selected, {}).get("api_url"):
                ping = _http_get(MCP_ENDPOINTS[selected]["api_url"], params={"op": "ping"}, timeout=6)
                if ping.get("status_code") and int(ping.get("status_code")) < 400:
                    # call match
                    resp = _http_get(MCP_ENDPOINTS[selected]["api_url"], params={"op": "match", "profile_id": user_profile.get("id")}, timeout=10)
                    return json.dumps({"from_mcp": resp}, indent=2)
            # fallback to local matching
            # reuse the logic from the main tool for consistency
            local_matches = []
            interests = set([i.lower() for i in (user_profile.get("interests") or [])])
            if selected == "job_finder":
                for job in MOCK_JOBS:
                    job_skills = set([s.lower() for s in job.get("skills", [])])
                    score = len(interests & job_skills)
                    if score > 0:
                        local_matches.append({"job": job, "score": score})
            else:
                for tr in MOCK_TRAININGS:
                    score = 0
                    title_lower = tr.get("title", "").lower()
                    if any(i in title_lower for i in interests):
                        score += 2
                    if score > 0:
                        local_matches.append({"training": tr, "score": score})
            local_matches = sorted(local_matches, key=lambda x: x.get("score", 0), reverse=True)
            return json.dumps({"local_matches": local_matches}, indent=2)
        except Exception as e:
            return json.dumps({"error": str(e)}, indent=2)
    return run_async(_match_async())
