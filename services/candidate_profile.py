"""
Candidate profile fetching for agent context placeholders.
"""

import json
from typing import Optional

from livekit import rtc

from app.config import Config  # type: ignore
from app.utils.logger import get_logger  # type: ignore

logger = get_logger(__name__)


async def fetch_candidate_profile(
    room: rtc.Room, config: Config, booking_token: Optional[str] = None
) -> Optional[dict]:
    """
    Fetch candidate application profile from MongoDB student_application_forms.
    Used to replace placeholders like {full_name}, {email}, {aadhaar_number} in agent context.

    Flow: booking_token -> interview_bookings (get user_id) -> student_application_forms (get form by user_id).

    Args:
        room: LiveKit room instance (used for metadata fallback)
        config: App config
        booking_token: From room name (interview_<token>) or room metadata

    Returns:
        Flat dict of application form fields (full_name, email, etc.) or None
    """
    try:
        user_id = None
        booking = None

        # 1) Prefer booking_token: get user_id from interview_bookings, then form from student_application_forms
        if booking_token:
            try:
                from app.services.booking_service import BookingService  # type: ignore
                from app.services.application_form_service import ApplicationFormService  # type: ignore
                booking_service = BookingService(config)
                form_service = ApplicationFormService(config)
                booking = booking_service.get_booking(booking_token)
                if booking and booking.get("user_id"):
                    user_id = str(booking["user_id"]).strip()
                    form = form_service.get_form_by_user_id(user_id)
                    if form:
                        # If form exists but missing full_name, use booking.name as fallback
                        if not form.get("full_name") and booking.get("name"):
                            form["full_name"] = booking.get("name")
                            logger.info(f"[OK] Candidate profile from form + booking name fallback (user_id={user_id}, full_name={form.get('full_name', '')})")
                        else:
                            logger.info(f"[OK] Candidate profile from student_application_forms (user_id={user_id}, full_name={form.get('full_name', '')})")
                        print(f"[OK] Candidate profile loaded for placeholders (e.g. {{full_name}})", flush=True)
                        return form
                    # No form found - build minimal profile from booking
                    if booking.get("name") or booking.get("email"):
                        minimal_profile = {}
                        if booking.get("name"):
                            minimal_profile["full_name"] = booking.get("name")
                        if booking.get("email"):
                            minimal_profile["email"] = booking.get("email")
                        logger.info(f"[OK] Candidate profile from booking (no form found, using booking name: {minimal_profile.get('full_name', 'N/A')})")
                        print(f"[OK] Candidate profile from booking (name: {minimal_profile.get('full_name', 'N/A')})", flush=True)
                        return minimal_profile if minimal_profile else None
                    logger.debug(f"No application form for user_id={user_id} and no name in booking")
            except ImportError as e:
                logger.debug(f"Services not available: {e}")
            except Exception as e:
                logger.warning(f"[WARN]  Fetch candidate profile via booking: {e}")

        # 2) Fallback: user_id or form_id from room metadata
        if hasattr(room, 'metadata') and room.metadata:
            try:
                metadata = json.loads(room.metadata)
                user_id = user_id or metadata.get('user_id') or metadata.get('userId')
                if user_id:
                    from app.services.application_form_service import ApplicationFormService  # type: ignore
                    form_service = ApplicationFormService(config)
                    form = form_service.get_form_by_user_id(str(user_id))
                    if form:
                        logger.info(f"[OK] Candidate profile from metadata user_id={user_id}")
                        return form
            except (json.JSONDecodeError, ImportError):
                pass
            except Exception as e:
                logger.warning(f"[WARN]  Fetch candidate profile from metadata: {e}")

        # 3) Final fallback: if we have booking but no user_id/form, use booking.name
        if booking and (booking.get("name") or booking.get("email")):
            minimal_profile = {}
            if booking.get("name"):
                minimal_profile["full_name"] = booking.get("name")
            if booking.get("email"):
                minimal_profile["email"] = booking.get("email")
            logger.info(f"[OK] Candidate profile from booking (no user_id/form, using booking name: {minimal_profile.get('full_name', 'N/A')})")
            print(f"[OK] Candidate profile from booking (name: {minimal_profile.get('full_name', 'N/A')})", flush=True)
            return minimal_profile if minimal_profile else None

        if not user_id:
            logger.info("📄 No booking_token or user_id — placeholders like {full_name} will not be replaced")
    except Exception as e:
        logger.warning(f"[WARN]  Error fetching candidate profile: {e}")
    return None
