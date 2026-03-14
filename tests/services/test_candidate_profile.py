import pytest
import sys
from unittest.mock import MagicMock
from services.candidate_profile import fetch_candidate_profile

@pytest.mark.asyncio
async def test_fetch_candidate_profile_success():
    """Test successful profile fetch from form service using sys.modules mocks."""
    mock_room = MagicMock()
    mock_config = MagicMock()
    
    # Access existing mocks from conftest
    mock_booking_mod = sys.modules['app.services.booking_service']
    mock_form_mod = sys.modules['app.services.application_form_service']
    
    # Configure them
    booking_svc = mock_booking_mod.BookingService.return_value
    booking_svc.get_booking.return_value = {"user_id": "user123", "name": "John"}
    
    form_svc = mock_form_mod.ApplicationFormService.return_value
    form_svc.get_form_by_user_id.return_value = {"full_name": "John Doe", "email": "john@doe.com"}
    
    profile = await fetch_candidate_profile(mock_room, mock_config, booking_token="token123")
    
    assert isinstance(profile, dict)
    assert profile["full_name"] == "John Doe"

@pytest.mark.asyncio
async def test_fetch_candidate_profile_booking_fallback():
    """Test fallback to booking name if form is missing."""
    mock_room = MagicMock()
    mock_config = MagicMock()
    
    mock_booking_mod = sys.modules['app.services.booking_service']
    mock_form_mod = sys.modules['app.services.application_form_service']
    
    mock_booking_mod.BookingService.return_value.get_booking.return_value = {"name": "John Booking", "email": "john@b.com"}
    mock_form_mod.ApplicationFormService.return_value.get_form_by_user_id.return_value = None
    
    profile = await fetch_candidate_profile(mock_room, mock_config, booking_token="token123")
    
    assert profile["full_name"] == "John Booking"
    assert profile["email"] == "john@b.com"

@pytest.mark.asyncio
async def test_fetch_candidate_profile_metadata_fallback():
    """Test fallback to room metadata if booking token fails."""
    mock_room = MagicMock()
    mock_room.metadata = '{"user_id": "meta123"}'
    mock_config = MagicMock()
    
    mock_form_mod = sys.modules['app.services.application_form_service']
    mock_form_mod.ApplicationFormService.return_value.get_form_by_user_id.return_value = {"full_name": "Meta User"}
    
    profile = await fetch_candidate_profile(mock_room, mock_config)
    
    assert profile["full_name"] == "Meta User"
