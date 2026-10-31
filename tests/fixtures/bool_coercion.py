def as_bool(value):
    return not not value


def store(value):
    flag = not not value
    return flag


def branch(value):
    if value:
        return "truthy"
    return "falsy"


def nested(value):
    return not not (value and 1)
