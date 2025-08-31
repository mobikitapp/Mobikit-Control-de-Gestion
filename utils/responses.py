from flask import jsonify
from typing import Dict, Any, Optional


def success_response(data: Any = None, message: str = None, status_code: int = 200):
    """
    Create a standardized success response
    
    Args:
        data: Response data
        message: Optional success message
        status_code: HTTP status code (default 200)
    
    Returns:
        Flask JSON response
    """
    response_data = {
        'success': True,
        'data': data
    }
    
    if message:
        response_data['message'] = message
    
    return jsonify(response_data), status_code


def error_response(message: str, status_code: int = 400, error_code: str = None):
    """
    Create a standardized error response
    
    Args:
        message: Error message
        status_code: HTTP status code (default 400)
        error_code: Optional error code for client handling
    
    Returns:
        Flask JSON response
    """
    response_data = {
        'success': False,
        'error': {
            'message': message
        }
    }
    
    if error_code:
        response_data['error']['code'] = error_code
    
    return jsonify(response_data), status_code


def validation_error_response(errors: Dict[str, Any], status_code: int = 422):
    """
    Create a validation error response
    
    Args:
        errors: Dictionary of validation errors
        status_code: HTTP status code (default 422)
    
    Returns:
        Flask JSON response
    """
    return jsonify({
        'success': False,
        'error': {
            'message': 'Validation failed',
            'validation_errors': errors
        }
    }), status_code


def not_found_response(resource: str = "Resource"):
    """
    Create a not found response
    
    Args:
        resource: Name of the resource that wasn't found
    
    Returns:
        Flask JSON response
    """
    return error_response(f"{resource} not found", 404, "NOT_FOUND")


def unauthorized_response(message: str = "Authentication required"):
    """
    Create an unauthorized response
    
    Args:
        message: Unauthorized message
    
    Returns:
        Flask JSON response
    """
    return error_response(message, 401, "UNAUTHORIZED")


def forbidden_response(message: str = "Access denied"):
    """
    Create a forbidden response
    
    Args:
        message: Forbidden message
    
    Returns:
        Flask JSON response
    """
    return error_response(message, 403, "FORBIDDEN")


def internal_error_response(message: str = "Internal server error"):
    """
    Create an internal server error response
    
    Args:
        message: Error message
    
    Returns:
        Flask JSON response
    """
    return error_response(message, 500, "INTERNAL_ERROR")