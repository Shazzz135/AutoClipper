from datetime import datetime, timedelta
import pytz
from typing import List, Optional, Dict, Any
from backend.core.config import settings

# Daily Posting Windows for YouTube Shorts (America/New_York / EST)
# Structured according to industry benchmarks for maximum engagement:
# - Monday: 6:00 PM – 9:00 PM (Target: 7:00 PM)
# - Tuesday: 6:00 PM – 10:00 PM (Target: 6:30 PM)
# - Wednesday: 6:00 PM – 10:00 PM (Target: 7:00 PM)
# - Thursday: 6:00 PM (or 3-5 PM, Target: 6:00 PM)
# - Friday: 3:00 PM – 7:00 PM (Top Peak Day, Target: 5:00 PM)
# - Saturday: 3:00 PM – 6:00 PM (Weekend Scroll, Target: 4:00 PM)
# - Sunday: 12:00 PM – 3:00 PM (Midday Unwind, Target: 1:30 PM)
WEEKDAY_OPTIMAL_SCHEDULE: Dict[int, Dict[str, Any]] = {
    0: {
        "hour": 19, "minute": 0,
        "window": "6:00 PM – 9:00 PM",
        "day_name": "Monday",
        "description": "Monday Evening Scroll"
    },
    1: {
        "hour": 18, "minute": 30,
        "window": "6:00 PM – 10:00 PM",
        "day_name": "Tuesday",
        "description": "Tuesday Prime Window"
    },
    2: {
        "hour": 19, "minute": 0,
        "window": "6:00 PM – 10:00 PM",
        "day_name": "Wednesday",
        "description": "Wednesday Mid-Week Steady"
    },
    3: {
        "hour": 18, "minute": 0,
        "window": "6:00 PM",
        "day_name": "Thursday",
        "description": "Thursday Afternoon/Evening"
    },
    4: {
        "hour": 17, "minute": 0,
        "window": "3:00 PM – 7:00 PM",
        "day_name": "Friday",
        "description": "Friday Peak Weekly Surge ⭐"
    },
    5: {
        "hour": 16, "minute": 0,
        "window": "3:00 PM – 6:00 PM",
        "day_name": "Saturday",
        "description": "Saturday Weekend Scroll"
    },
    6: {
        "hour": 13, "minute": 30,
        "window": "12:00 PM – 3:00 PM",
        "day_name": "Sunday",
        "description": "Sunday Midday / Afternoon"
    }
}

class PostingScheduler:
    def __init__(self):
        self.timezone = pytz.timezone(settings.YOUTUBE_TIMEZONE)

    def get_all_occupied_slots(self, extra_occupied: Optional[List[datetime]] = None) -> List[datetime]:
        """
        Combines occupied publish times from both:
        1. Live YouTube channel scheduled videos (via Data API publishAt)
        2. Local queue clips already assigned to future slots (state.clips)
        """
        occupied: List[datetime] = []

        # 1. Query YouTube Channel for scheduled videos
        try:
            from backend.uploader.youtube import uploader
            yt_times = uploader.get_scheduled_publish_times()
            occupied.extend(yt_times)
        except Exception:
            pass

        # 2. Check local clips in state
        try:
            from backend.core.state import state
            for clip in state.clips.values():
                if clip.get("status") in ["PENDING_REVIEW", "APPROVED", "UPLOADING", "UPLOADED"]:
                    slot_iso = clip.get("scheduled_slot_iso")
                    if slot_iso:
                        try:
                            clean_iso = slot_iso.replace("Z", "+00:00")
                            dt = datetime.fromisoformat(clean_iso)
                            occupied.append(dt)
                        except Exception:
                            pass
        except Exception:
            pass

        if extra_occupied:
            occupied.extend(extra_occupied)

        return occupied

    def get_next_available_slot(self, occupied_slots: Optional[List[datetime]] = None) -> datetime:
        """
        Finds the next optimal posting slot aiming for exactly 1 post per day.
        Checks both live YouTube account schedules and local clips to prevent duplicate/overlapping uploads.
        """
        now = datetime.now(self.timezone)
        all_occupied = self.get_all_occupied_slots(occupied_slots)

        # Convert all occupied datetimes to the local timezone
        occupied_local: List[datetime] = []
        occupied_dates = set()

        for dt in all_occupied:
            try:
                if dt.tzinfo is None:
                    loc_dt = self.timezone.localize(dt)
                else:
                    loc_dt = dt.astimezone(self.timezone)
                occupied_local.append(loc_dt)
                occupied_dates.add(loc_dt.date())
            except Exception:
                pass

        # Check up to 30 days into the future to find the first free daily window
        for day_offset in range(30):
            target_date = (now + timedelta(days=day_offset)).date()
            weekday = target_date.weekday()
            slot_config = WEEKDAY_OPTIMAL_SCHEDULE[weekday]

            slot_dt = self.timezone.localize(
                datetime(target_date.year, target_date.month, target_date.day,
                         slot_config["hour"], slot_config["minute"], 0)
            )

            # Rule 1: Slot must be at least 15 minutes in the future (YouTube API publishAt constraint)
            if slot_dt <= now + timedelta(minutes=15):
                continue

            # Rule 2: Strictly 1 post per day: Skip if target date already has a scheduled video
            if target_date in occupied_dates:
                continue

            # Rule 3: Anti-collision: No other upload within 4 hours
            has_collision = any(abs((slot_dt - occ).total_seconds()) < 14400 for occ in occupied_local)
            if has_collision:
                continue

            return slot_dt

        # Fallback if somehow 30 days are full: Day 31 at Friday default time
        fallback_date = (now + timedelta(days=31)).date()
        return self.timezone.localize(
            datetime(fallback_date.year, fallback_date.month, fallback_date.day, 17, 0, 0)
        )

    def get_slot_info(self, dt: datetime) -> Dict[str, Any]:
        """Returns metadata description for an assigned slot."""
        loc_dt = dt.astimezone(self.timezone)
        weekday = loc_dt.weekday()
        config = WEEKDAY_OPTIMAL_SCHEDULE[weekday]
        return {
            "iso": self.format_iso(loc_dt),
            "display": loc_dt.strftime("%I:%M %p (%a, %b %d)"),
            "day": config["day_name"],
            "window": config["window"],
            "description": config["description"]
        }

    def get_upcoming_schedule_preview(self, days: int = 7) -> List[Dict[str, Any]]:
        """
        Builds a day-by-day status calendar of the next N days showing optimal times
        and whether each day is Free, Reserved Locally, or Scheduled on YouTube.
        """
        now = datetime.now(self.timezone)
        occupied = self.get_all_occupied_slots()

        # Map occupied by date
        occupied_by_date: Dict[Any, str] = {}
        for occ in occupied:
            try:
                loc = occ.astimezone(self.timezone) if occ.tzinfo else self.timezone.localize(occ)
                occupied_by_date[loc.date()] = loc.strftime("%I:%M %p")
            except Exception:
                pass

        calendar = []
        for d in range(days):
            t_date = (now + timedelta(days=d)).date()
            weekday = t_date.weekday()
            cfg = WEEKDAY_OPTIMAL_SCHEDULE[weekday]
            slot_time = self.timezone.localize(
                datetime(t_date.year, t_date.month, t_date.day, cfg["hour"], cfg["minute"], 0)
            )

            is_past = slot_time <= now + timedelta(minutes=15)
            is_occupied = t_date in occupied_by_date

            status = "FREE"
            if is_occupied:
                status = "OCCUPIED"
            elif is_past:
                status = "PAST"

            calendar.append({
                "date": t_date.strftime("%Y-%m-%d"),
                "display_date": t_date.strftime("%a, %b %d"),
                "day_name": cfg["day_name"],
                "optimal_time": cfg["time"] if "time" in cfg else f"{cfg['hour']:02d}:{cfg['minute']:02d}",
                "optimal_time_display": slot_time.strftime("%I:%M %p"),
                "window": cfg["window"],
                "description": cfg["description"],
                "status": status,
                "scheduled_at": occupied_by_date.get(t_date)
            })

        return calendar

    def format_iso(self, dt: datetime) -> str:
        """Converts datetime to ISO-8601 UTC string required by YouTube API."""
        utc_dt = dt.astimezone(pytz.utc)
        return utc_dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")

scheduler = PostingScheduler()
