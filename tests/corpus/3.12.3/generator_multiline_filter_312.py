def multiline_filter(values, excluded):
    return tuple(value for value in values
                 if value not in excluded)
