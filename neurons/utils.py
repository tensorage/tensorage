def validate_min_max_range(value, min_value, max_value):
    """
    Purpose:
        Make sure if value is in range of min_value and max_value.
    """
    min_value = min(min_value, max_value)
    max_value = max(min_value, max_value)

    if value < min_value:
        value = min_value
    elif value > max_value:
        value = max_value
    
    return value
# end def