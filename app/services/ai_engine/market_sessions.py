import logging

from datetime import datetime, timezone

from typing import Any, Dict, List



logger = logging.getLogger(__name__)



# Major forex trading sessions in UTC (decimal hours). Sydney wraps past

# midnight, handled explicitly below.

SESSIONS = [

    {"name": "Sydney", "start": 22.0, "end": 7.0, "color": "#f59e0b"},

    {"name": "Tokyo", "start": 0.0, "end": 9.0, "color": "#ef4444"},

    {"name": "London", "start": 8.0, "end": 17.0, "color": "#3b82f6"},

    {"name": "New York", "start": 13.0, "end": 22.0, "color": "#22c55e"},

]





def get_sessions(now: datetime | None = None) -> Dict[str, Any]:

    """Return the current active forex session(s) in UTC.



    Each session reports whether it is currently open and a 0..1 progress

    through its window, so the UI can render a session ribbon.

    """

    now = now or datetime.now(timezone.utc)

    hour = now.hour + now.minute / 60.0 + now.second / 3600.0



    out: List[Dict[str, Any]] = []

    for s in SESSIONS:

        start, end = s["start"], s["end"]

        wraps = start > end

        if wraps:

            active = hour >= start or hour < end

        else:

            active = start <= hour < end



        progress = 0.0

        if active:

            if wraps:

                if hour >= start:

                    progress = (hour - start) / (24.0 - start)

                else:

                    progress = (hour + 24.0 - start) / (24.0 - start)

            else:

                progress = (hour - start) / (end - start)

            progress = max(0.0, min(1.0, progress))



        out.append(

            {

                "name": s["name"],

                "color": s["color"],

                "start": start,

                "end": end,

                "active": active,

                "progress": round(progress, 3),

            }

        )



    active_names = [s["name"] for s in out if s["active"]]

    return {

        "current_utc": now.strftime("%H:%M:%S"),

        "current_utc_hour": round(hour, 2),

        "sessions": out,

        "active": active_names,

    }
