from datetime import datetime, timedelta
import pytz
from typing import List, Optional, Dict, Any
from backend.core.config import settings

# Daily 3-Slot Optimal Posting Windows for YouTube Shorts (America/New_York / EST)
# Structured according to industry benchmarks for maximum engagement and 3x daily distribution:
# - Slot 1 (Midday / Lunch): 12:00 PM EST (11:30 AM weekends) - US Lunch Scroll + Western Europe Evening Peak
# - Slot 2 (After-School / Commute): 3:30 PM EST (3:00 PM weekends) - Afternoon commute & after-school scroll
# - Slot 3 (Prime Evening Peak): 7:00 PM EST (6:30 PM weekends) - Nationwide peak leisure & gaming hours ⭐

WEEKDAY_SLOTS = [
    {"hour": 12, "minute": 0, "window": "12:00 PM – 1:00 PM", "description": "Midday Lunch Scroll (US + EU Peak)"},
    {"hour": 15, "minute": 30, "window": "3:30 PM – 4:30 PM", "description": "After-School & Commute Window"},
    {"hour": 19, "minute": 0, "window": "6:30 PM – 8:30 PM", "description": "Prime Evening Gaming Peak ⭐"}
]

WEEKEND_SLOTS = [
    {"hour": 11, "minute": 30, "window": "11:00 AM – 1:00 PM", "description": "Weekend Morning Scroll"},
    {"hour": 15, "minute": 0, "window": "2:30 PM – 4:30 PM", "description": "Weekend Afternoon Leisure"},
    {"hour": 18, "minute": 30, "window": "6:00 PM – 8:00 PM", "description": "Weekend Prime Evening ⭐"}
]

DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

def get_slots_for_weekday(weekday: int) -> List[Dict[str, Any]]:
    return WEEKEND_SLOTS if weekday in (5, 6) else WEEKDAY_SLOTS

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
        Finds the next optimal posting slot among the 3 daily peak windows.
        Picks the earliest upcoming slot that:
        1. Is at least 15 minutes in the future (YouTube API publishAt constraint).
        2. Has no other scheduled video within 2.5 hours (prevents algorithmic cannibalization).
        If today's 3 slots are taken, automatically rolls over to the next day's Slot 1.
        """
        now = datetime.now(self.timezone)
        all_occupied = self.get_all_occupied_slots(occupied_slots)

        # Convert all occupied datetimes to the local timezone
        occupied_local: List[datetime] = []
        for dt in all_occupied:
            try:
                if dt.tzinfo is None:
                    loc_dt = self.timezone.localize(dt)
                else:
                    loc_dt = dt.astimezone(self.timezone)
                occupied_local.append(loc_dt)
            except Exception:
                pass

        # Check up to 30 days into the future for the first free slot among the 3 daily windows
        for day_offset in range(30):
            target_date = (now + timedelta(days=day_offset)).date()
            weekday = target_date.weekday()
            daily_slots = get_slots_for_weekday(weekday)

            for slot_cfg in daily_slots:
                slot_dt = self.timezone.localize(
                    datetime(target_date.year, target_date.month, target_date.day,
                             slot_cfg["hour"], slot_cfg["minute"], 0)
                )

                # Rule 1: Slot must be at least 15 minutes in the future
                if slot_dt <= now + timedelta(minutes=15):
                    continue

                # Rule 2: Anti-collision: No other upload within 2.5 hours (9,000 seconds)
                has_collision = any(abs((slot_dt - occ).total_seconds()) < 9000 for occ in occupied_local)
                if has_collision:
                    continue

                return slot_dt

        # Fallback if somehow 30 days are full
        fallback_date = (now + timedelta(days=31)).date()
        return self.timezone.localize(
            datetime(fallback_date.year, fallback_date.month, fallback_date.day, 12, 0, 0)
        )

    def get_slot_info(self, dt: datetime) -> Dict[str, Any]:
        """Returns metadata description for an assigned slot."""
        loc_dt = dt.astimezone(self.timezone)
        weekday = loc_dt.weekday()
        day_name = DAY_NAMES[weekday]
        slots = get_slots_for_weekday(weekday)

        # Match the closest slot config by hour/minute
        best_cfg = slots[0]
        min_diff = float("inf")
        for s in slots:
            slot_mins = s["hour"] * 60 + s["minute"]
            target_mins = loc_dt.hour * 60 + loc_dt.minute
            diff = abs(slot_mins - target_mins)
            if diff < min_diff:
                min_diff = diff
                best_cfg = s

        return {
            "iso": self.format_iso(loc_dt),
            "display": loc_dt.strftime("%I:%M %p (%a, %b %d)"),
            "day": day_name,
            "window": best_cfg["window"],
            "description": best_cfg["description"]
        }

    def get_upcoming_schedule_preview(self, days: int = 7) -> List[Dict[str, Any]]:
        """
        Builds a day-by-day status calendar of the next N days showing optimal times
        and whether each slot is Free, Reserved Locally, or Scheduled on YouTube.
        """
        now = datetime.now(self.timezone)
        occupied = self.get_all_occupied_slots()

        occupied_local: List[datetime] = []
        for occ in occupied:
            try:
                loc = occ.astimezone(self.timezone) if occ.tzinfo else self.timezone.localize(occ)
                occupied_local.append(loc)
            except Exception:
                pass

        calendar = []
        for d in range(days):
            t_date = (now + timedelta(days=d)).date()
            weekday = t_date.weekday()
            slots = get_slots_for_weekday(weekday)
            day_name = DAY_NAMES[weekday]

            for s_idx, cfg in enumerate(slots, 1):
                slot_time = self.timezone.localize(
                    datetime(t_date.year, t_date.month, t_date.day, cfg["hour"], cfg["minute"], 0)
                )

                is_past = slot_time <= now + timedelta(minutes=15)
                matched_occ = next((occ for occ in occupied_local if abs((slot_time - occ).total_seconds()) < 7200), None)

                status = "FREE"
                if matched_occ:
                    status = "OCCUPIED"
                elif is_past:
                    status = "PAST"

                calendar.append({
                    "date": t_date.strftime("%Y-%m-%d"),
                    "display_date": t_date.strftime("%a, %b %d"),
                    "day_name": day_name,
                    "slot_number": s_idx,
                    "optimal_time": f"{cfg['hour']:02d}:{cfg['minute']:02d}",
                    "optimal_time_display": slot_time.strftime("%I:%M %p"),
                    "window": cfg["window"],
                    "description": cfg["description"],
                    "status": status,
                    "scheduled_at": matched_occ.strftime("%I:%M %p") if matched_occ else None
                })

        return calendar

    def format_iso(self, dt: datetime) -> str:
        """Converts datetime to ISO-8601 UTC string required by YouTube API."""
        utc_dt = dt.astimezone(pytz.utc)
        return utc_dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")

scheduler = PostingScheduler()
