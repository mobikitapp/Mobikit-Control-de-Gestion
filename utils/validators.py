import re
from typing import Any, Optional


def validate_not_empty(value: Any, field_name: str = "Field") -> str:
    """
    Validate that a value is not empty
    
    Args:
        value: Value to validate
        field_name: Name of the field for error messages
    
    Returns:
        Cleaned string value
    
    Raises:
        ValueError: If value is empty
    """
    if value is None:
        raise ValueError(f"{field_name} is required")
    
    if isinstance(value, str):
        cleaned = value.strip()
        if not cleaned:
            raise ValueError(f"{field_name} cannot be empty")
        return cleaned
    
    if not value:
        raise ValueError(f"{field_name} is required")
    
    return str(value)


def validate_email(email: str, required: bool = True) -> Optional[str]:
    """
    Validate email format
    
    Args:
        email: Email to validate
        required: Whether email is required
    
    Returns:
        Cleaned email or None
    
    Raises:
        ValueError: If email format is invalid
    """
    if not email:
        if required:
            raise ValueError("Email is required")
        return None
    
    email = email.strip().lower()
    
    # Basic email regex
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not re.match(pattern, email):
        raise ValueError("Invalid email format")
    
    return email


def validate_phone(phone: str, required: bool = False) -> Optional[str]:
    """
    Validate and clean phone number
    
    Args:
        phone: Phone number to validate
        required: Whether phone is required
    
    Returns:
        Cleaned phone number or None
    
    Raises:
        ValueError: If phone format is invalid
    """
    if not phone:
        if required:
            raise ValueError("Phone number is required")
        return None
    
    # Remove all non-digit characters
    cleaned = re.sub(r'\D', '', phone.strip())
    
    if len(cleaned) < 8:
        raise ValueError("Phone number too short")
    
    return cleaned


def validate_rut(rut: str, required: bool = True) -> Optional[str]:
    """
    Validate Chilean RUT format
    
    Args:
        rut: RUT to validate
        required: Whether RUT is required
    
    Returns:
        Cleaned RUT or None
    
    Raises:
        ValueError: If RUT format is invalid
    """
    if not rut:
        if required:
            raise ValueError("RUT is required")
        return None
    
    # Clean RUT: remove dots, hyphens, and spaces
    cleaned = re.sub(r'[.\-\s]', '', rut.strip()).upper()
    
    if len(cleaned) < 8 or len(cleaned) > 9:
        raise ValueError("Invalid RUT length")
    
    # Basic format check
    if not re.match(r'^\d{7,8}[0-9K]$', cleaned):
        raise ValueError("Invalid RUT format")
    
    return cleaned


def validate_positive_number(value: Any, field_name: str = "Value") -> float:
    """
    Validate that a value is a positive number
    
    Args:
        value: Value to validate
        field_name: Name of the field for error messages
    
    Returns:
        Float value
    
    Raises:
        ValueError: If value is not a positive number
    """
    try:
        num_value = float(value)
    except (ValueError, TypeError):
        raise ValueError(f"{field_name} must be a valid number")
    
    if num_value <= 0:
        raise ValueError(f"{field_name} must be positive")
    
    return num_value


def validate_non_negative_number(value: Any, field_name: str = "Value") -> float:
    """
    Validate that a value is a non-negative number
    
    Args:
        value: Value to validate
        field_name: Name of the field for error messages
    
    Returns:
        Float value
    
    Raises:
        ValueError: If value is not a non-negative number
    """
    try:
        num_value = float(value)
    except (ValueError, TypeError):
        raise ValueError(f"{field_name} must be a valid number")
    
    if num_value < 0:
        raise ValueError(f"{field_name} cannot be negative")
    
    return num_value


def validate_integer(value: Any, field_name: str = "Value", min_value: int = None, max_value: int = None) -> int:
    """
    Validate that a value is an integer within optional bounds
    
    Args:
        value: Value to validate
        field_name: Name of the field for error messages
        min_value: Optional minimum value
        max_value: Optional maximum value
    
    Returns:
        Integer value
    
    Raises:
        ValueError: If value is not a valid integer or out of bounds
    """
    try:
        int_value = int(value)
    except (ValueError, TypeError):
        raise ValueError(f"{field_name} must be a valid integer")
    
    if min_value is not None and int_value < min_value:
        raise ValueError(f"{field_name} must be at least {min_value}")
    
    if max_value is not None and int_value > max_value:
        raise ValueError(f"{field_name} must be at most {max_value}")
    
    return int_value


def validate_string_length(value: str, field_name: str = "Field", 
                         min_length: int = None, max_length: int = None) -> str:
    """
    Validate string length
    
    Args:
        value: String to validate
        field_name: Name of the field for error messages
        min_length: Optional minimum length
        max_length: Optional maximum length
    
    Returns:
        Validated string
    
    Raises:
        ValueError: If string length is invalid
    """
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    
    if min_length is not None and len(value) < min_length:
        raise ValueError(f"{field_name} must be at least {min_length} characters long")
    
    if max_length is not None and len(value) > max_length:
        raise ValueError(f"{field_name} must be at most {max_length} characters long")
    
    return value