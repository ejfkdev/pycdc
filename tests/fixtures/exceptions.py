def risky():
    try:
        x = 1 / 0
    except ZeroDivisionError as e:
        print(e)
    except (ValueError, TypeError):
        pass
    else:
        print("ok")
    finally:
        print("done")

def raiser():
    raise ValueError("bad")

def bare():
    try:
        pass
    except:
        raise

def cleaner():
    try:
        return 1
    finally:
        print("bye")
